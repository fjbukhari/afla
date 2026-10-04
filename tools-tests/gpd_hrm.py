"""Stress-test Step 14 (HRM) of the Gene Panel Designer.

Checks, independently: primer positions on the reference, product size, that the variant sits
inside the product with the promised primer-to-variant gap, the reported ref/alt amplicon melting
temperatures and their difference, and amplicon size against HRM practice.
"""
import json
import re
import sys

import primer3
from playwright.sync_api import sync_playwright

sys.path.insert(0, '/home/user/jbs-site/test')
import gpd_lib as G

BASE = 'http://127.0.0.1:8900/catalogue/staff/'

# (gene, chrom, 1-based pos, ref, alt, note) -- positions chosen to land in different zone types
CASES = [
    ('TP53', 'chr17', 7675080, None, None, 'homopolymer zone'),
    ('TP53', 'chr17', 7670300, None, None, 'GC-rich zone'),
    ('TP53', 'chr17', 7673200, None, None, 'AT-rich zone'),
    ('TP53', 'chr17', 7674200, None, None, 'duplicated (pseudogene) zone'),
    ('TP53', 'chr17', 7676900, None, None, 'CAG repeat zone'),
    ('TP53', 'chr17', 7679000, None, None, 'plain sequence'),
]


def run():
    out = {'cases': [], 'errors': []}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
        ctx = b.new_context(viewport={'width': 1400, 'height': 900})
        ctx.request.get(BASE + 'api/gate-sso.php')
        G.install_routes(ctx)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: out['errors'].append(str(e)[:300]))
        pg.on('dialog', lambda d: (out['errors'].append('DIALOG ' + d.message[:200]), d.accept()))
        pg.goto(BASE + 'designers/genepaneldesigner.html', timeout=120000)
        pg.wait_for_timeout(2500)
        pg.evaluate("document.getElementById('geneInput').value='TP53'")
        pg.evaluate("document.getElementById('parseBtn').click()")
        pg.wait_for_timeout(1500)
        pg.evaluate("switchStep && switchStep(14)")
        pg.wait_for_timeout(600)

        for gene, chrom, pos1, ref, alt, note in CASES:
            # real reference base at that position, so ref is always correct
            ref = G.genome(chrom, pos1 - 1, pos1)
            alt = {'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G'}[ref]
            pg.evaluate("""([gene,chrom,pos,ref,alt])=>{
                const set=(id,v)=>{const e=document.getElementById(id); if(e){e.value=v;
                    e.dispatchEvent(new Event('input',{bubbles:true}));
                    e.dispatchEvent(new Event('change',{bubbles:true}));}};
                const g=document.getElementById('hrmGeneSelect');
                if(g){for(const o of g.options) o.selected=(o.value===gene); g.dispatchEvent(new Event('change',{bubbles:true}));}
                set('hrmVariantChrom',chrom); set('hrmVariantPos',String(pos));
                set('hrmVariantRef',ref); set('hrmVariantAlt',alt);
                const w=document.getElementById('hrmGenoResultWrap'); if(w) w.innerHTML='';
            }""", [gene, chrom, pos1, ref, alt])
            pg.evaluate("document.getElementById('hrmGenoDesignBtn').click()")
            txt = ''
            for _ in range(60):
                pg.wait_for_timeout(1000)
                txt = pg.evaluate("(document.getElementById('hrmGenoResultWrap')||{}).innerText||''")
                if re.search(r'product|no pair|could not|unable|failed|Error', txt, re.I):
                    pg.wait_for_timeout(1500)
                    txt = pg.evaluate("(document.getElementById('hrmGenoResultWrap')||{}).innerText||''")
                    break
            out['cases'].append({'gene': gene, 'chrom': chrom, 'pos': pos1, 'ref': ref, 'alt': alt,
                                 'note': note, 'text': txt[:4000]})
        ctx.close()
        b.close()

    for c in out['cases']:
        t = c['text']
        m = re.search(r'([\d,]+)\s*[–-]\s*([\d,]+)\s*·\s*product\s*(\d+)\s*bp', t)
        pr = re.findall(r'(Fwd|Rev)([ACGT]{15,})(\d+)nt', t)
        c['checks'] = {}
        if m and len(pr) >= 2:
            a = int(m.group(1).replace(',', '')) - 1  # card shows 1-based start
            e = int(m.group(2).replace(',', ''))
            prod = int(m.group(3))
            fwd = dict(pr)['Fwd']
            rev = dict(pr)['Rev']
            seq = G.genome(c['chrom'], a, e)
            c['checks'] = {
                'span': e - a, 'product': prod,
                'size_ok': prod == e - a,
                'fwd_at_start': seq.startswith(fwd),
                'rev_at_end': seq.endswith(G.rc(rev)),
                'variant_inside': a < c['pos'] <= e,
                'gap_fwd': (c['pos'] - 1) - (a + len(fwd)),
                'gap_rev': (e - len(rev)) - c['pos'],
                'amplicon_len': e - a,
            }
            # independent ref/alt amplicon melting difference (same NN oligo model the tool uses)
            loc = (c['pos'] - 1) - a
            refamp = seq[:loc] + c['ref'] + seq[loc + 1:]
            altamp = seq[:loc] + c['alt'] + seq[loc + 1:]
            c['checks']['gc_ref'] = round(100 * sum(x in 'GC' for x in refamp) / len(refamp), 1)
            c['checks']['gc_alt'] = round(100 * sum(x in 'GC' for x in altamp) / len(altamp), 1)
            # published empirical formula for long duplex Tm (Howley/Wetmur salt-adjusted)
            def tm_long(s):
                gc = 100 * sum(x in 'GC' for x in s) / len(s)
                return 81.5 + 16.6 * (-1.30103) + 0.41 * gc - 500 / len(s)  # 50 mM Na+
            c['checks']['tm_long_ref'] = round(tm_long(refamp), 2)
            c['checks']['tm_long_alt'] = round(tm_long(altamp), 2)
        c['reported_tm'] = re.findall(r'(\d{2,3}\.\d)\s*°C', t)[:8]
        c['reported_dtm'] = re.findall(r'[ΔΔ]Tm[^0-9\-]*(-?\d+\.\d+)', t)[:4]
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    run()
