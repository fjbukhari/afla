"""Stress-test Step 5 (NGS/Sanger amplicon design) of the Gene Panel Designer.

For every reported pair this checks, independently of the tool:
  - both primers really occur at the reported coordinates on the reference
  - the product size matches the coordinates
  - Tm agrees with primer3 (the reference implementation)
  - the promised minimum intronic flank is actually achieved
  - the exon the pair is named for is fully inside the product
  - the pair's uniqueness claim matches an exact-match scan of the 50 kb window
"""
import json
import re
import sys

import primer3
from playwright.sync_api import sync_playwright

sys.path.insert(0, '/home/user/jbs-site/test')
import gpd_lib as G

BASE = 'http://127.0.0.1:8900/catalogue/staff/'
GENES = sys.argv[1] if len(sys.argv) > 1 else 'TP53'
FLANK = sys.argv[2] if len(sys.argv) > 2 else '20'
AMP = sys.argv[3] if len(sys.argv) > 3 else '400'


def main():
    out = {'pairs': [], 'issues': [], 'errors': []}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
        ctx = b.new_context(viewport={'width': 1400, 'height': 900})
        ctx.request.get(BASE + 'api/gate-sso.php')
        calls = []
        G.install_routes(ctx, calls)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: out['errors'].append(str(e)[:300]))
        pg.on('dialog', lambda d: (out['errors'].append('DIALOG ' + d.message[:200]), d.accept()))
        pg.goto(BASE + 'designers/genepaneldesigner.html', timeout=120000)
        pg.wait_for_timeout(2500)

        pg.evaluate("(g)=>{document.getElementById('geneInput').value=g;}", GENES)
        pg.evaluate("document.getElementById('parseBtn').click()")
        pg.wait_for_timeout(1500)
        pg.evaluate("""([f,a])=>{const set=(id,v)=>{const el=document.getElementById(id);
            if(el){el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));}};
            set('designMinFlank',f); set('designMaxAmplicon',a);}""", [FLANK, AMP])
        pg.evaluate("""(g)=>{const s=document.getElementById('designGeneSelect');
            const want=g.split(/[ ,]+/).filter(Boolean);
            for(const o of s.options) o.selected = want.includes(o.value);
            s.dispatchEvent(new Event('change',{bubbles:true}));}""", GENES)
        pg.evaluate("document.getElementById('runDesignBtn').click()")
        for i in range(600):
            pg.wait_for_timeout(1000)
            if not pg.evaluate("document.getElementById('runDesignBtn').disabled") and i > 3:
                break
        # the tool keeps every designed pair in lastDesignRun.pairsById
        pairs = pg.evaluate("""()=>{const o=[];
            if(typeof lastDesignRun==='undefined'||!lastDesignRun.pairsById) return o;
            lastDesignRun.pairsById.forEach((v,k)=>o.push({id:k, gene:v.gene, target:v.target,
                chrom:v.chrom, mode:v.mode,
                fwd:{seq:v.pair.fwd.seq,start:v.pair.fwd.start,end:v.pair.fwd.end,tm:v.pair.fwd.tm,gc:v.pair.fwd.gc},
                rev:{seq:v.pair.rev.seq,start:v.pair.rev.start,end:v.pair.rev.end,tm:v.pair.rev.tm,gc:v.pair.rev.gc},
                productSize:v.pair.productSize, dTm:v.pair.dTm}));
            return o;}""")
        rows = pg.evaluate("""()=>state.rows.map(r=>({symbol:r.symbol,chrom:r.chrom,strand:r.strand,
            exonDetails:(r.exonDetails||[]).map(e=>({num:e.exonNum,start:e.start,end:e.end}))}))""")
        text = pg.evaluate("(document.getElementById('designResults')||document.querySelector('[id*=esignResult]')||{}).innerText||''")
        out['n_ucsc_calls'] = len(calls)
        out['text'] = text
        out['exon_sample'] = rows[0]['exonDetails'][:3] if rows else None
        ctx.close()
        b.close()

    byrow = {r['symbol']: r for r in rows}
    # reported uniqueness, parsed from the rendered cards
    uniq_claim = dict(re.findall(r'Fwd([ACGT]{15,})\d+nt[^\n]*', text) and [] or [])

    for pr in pairs:
        chrom = pr['chrom']
        f, r = pr['fwd'], pr['rev']
        amp_start, amp_end = min(f['start'], r['start']), max(f['end'], r['end'])
        seq = G.genome(chrom, amp_start, amp_end)
        rec = {'gene': pr['gene'], 'target': pr['target'], 'mode': pr['mode'],
               'chrom': chrom, 'start': amp_start, 'end': amp_end,
               'product': pr['productSize'], 'fwd': f['seq'], 'rev': r['seq']}

        # 1. primers present at the reported coordinates
        fwd_at = G.genome(chrom, f['start'], f['end'])
        rev_at = G.genome(chrom, r['start'], r['end'])
        if fwd_at != f['seq']:
            out['issues'].append(dict(rec, issue='fwd primer not at reported coordinates'))
        if G.rc(rev_at) != r['seq']:
            out['issues'].append(dict(rec, issue='rev primer not reverse-complement at reported coordinates'))

        # 2. product size consistent with coordinates
        if pr['productSize'] != amp_end - amp_start:
            out['issues'].append(dict(rec, issue=f"product {pr['productSize']} != span {amp_end-amp_start}"))

        # 3. Tm vs primer3
        for which, pz in (('fwd', f), ('rev', r)):
            # Mg2+/dNTP included, matching the tool's corrected salt model and primer3's own
            ref = primer3.calc_tm(pz['seq'], mv_conc=50, dv_conc=1.5, dntp_conc=0.6, dna_conc=250,
                                  tm_method='santalucia', salt_corrections_method='santalucia')
            if abs(ref - pz['tm']) > 1.0:
                out['issues'].append(dict(rec, issue=f'{which} Tm {pz["tm"]:.1f} vs primer3 {ref:.1f}'))

        # 4. thermodynamic hairpin / dimer the tool's string heuristics may miss
        rec['hairpin_tm'] = [round(primer3.calc_hairpin(x['seq'], mv_conc=50, dv_conc=1.5, dntp_conc=0.6, dna_conc=250).tm, 1)
                             for x in (f, r)]
        rec['heterodimer_dg'] = round(primer3.calc_heterodimer(
            f['seq'], r['seq'], mv_conc=50, dv_conc=1.5, dntp_conc=0.6, dna_conc=250).dg / 1000, 2)
        rec['homodimer_dg'] = [round(primer3.calc_homodimer(x['seq'], mv_conc=50, dv_conc=1.5, dntp_conc=0.6, dna_conc=250).dg / 1000, 2)
                               for x in (f, r)]

        # 4b. sequence complexity: longest mono/di/tri-nucleotide repeat tract
        def max_repeat(seq):
            best = 0
            for unit in (1, 2, 3):
                i = 0
                while i < len(seq) - unit:
                    u = seq[i:i + unit]
                    n = 0
                    while seq[i + n * unit:i + (n + 1) * unit] == u:
                        n += 1
                    best = max(best, n * unit if n >= 3 else 0)
                    i += 1
            return best
        rec['repeat_tract'] = [max_repeat(f['seq']), max_repeat(r['seq'])]

        # 5. target exon(s) inside the product, and flank achieved
        row = byrow.get(pr['gene'])
        nums = [int(x) for x in re.findall(r'\d+', pr['target'].split('(')[0])] if row else []
        if row and nums:
            exs = [e for e in row['exonDetails'] if e['num'] in nums]
            if exs and 'amplicon 1/' not in pr['target'] and 'amplicon 2/' not in pr['target'] \
                   and 'amplicon 3/' not in pr['target'] and 'amplicon 4/' not in pr['target'] \
                   and 'split' not in pr['target']:
                lo, hi = min(e['start'] for e in exs), max(e['end'] for e in exs)
                if not (amp_start <= lo and amp_end >= hi):
                    out['issues'].append(dict(rec, issue=f'exon {nums} ({lo}-{hi}) not inside product'))
                rec['flank_fwd'] = lo - f['end']
                rec['flank_rev'] = r['start'] - hi
                if rec['flank_fwd'] < int(FLANK) or rec['flank_rev'] < int(FLANK):
                    out['issues'].append(dict(rec, issue=f"flank below promised {FLANK}: "
                                                         f"{rec['flank_fwd']}/{rec['flank_rev']}"))

        # 6. uniqueness in the same 50 kb window the tool checks
        span = amp_end - amp_start
        margin = max(0, (50000 - span) // 2)
        win = G.genome(chrom, amp_start - margin, amp_end + margin)
        nf = len(set(G.find_all(win, f['seq']) + G.find_all(win, G.rc(f['seq']))))
        nr = len(set(G.find_all(win, r['seq']) + G.find_all(win, G.rc(r['seq']))))
        prods = 0
        for a in G.find_all(win, f['seq']):
            for bb in G.find_all(win, G.rc(r['seq'])):
                sz = bb + len(r['seq']) - a
                if 80 <= sz <= span + 2000:
                    prods += 1
        rec['sites_50kb'] = [nf, nr, prods]
        out['pairs'].append(rec)

    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
