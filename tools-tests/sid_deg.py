"""Species ID degenerate-primer rules: at most 2 ambiguous positions, never within 3 bases of the
3' end (checked for forward AND reverse primers, where the 3' end is the other end of the window)."""
import sys, json
sys.path.insert(0,'/home/user/jbs-site/test'); import gpd_lib as G
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8900/catalogue/staff/'
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx=b.new_context(); ctx.request.get(BASE+'api/gate-sso.php'); G.install_routes(ctx)
    pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:250]))
    pg.goto(BASE+'designers/species-id-primer-designer.html',timeout=120000); pg.wait_for_timeout(2000)
    out=pg.evaluate("""()=>{
      const IUP='RYSWKMBDHVN';
      const rnd=(n,seed)=>{let s=seed;const r=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff;};
        return Array.from({length:n},()=>'ACGT'[Math.floor(r()*4)]).join('');};
      const results=[];
      for(let trial=0; trial<200; trial++){
        const L=60, seq=rnd(L,trial+11);
        // 10 aligned copies; make chosen columns vary in exactly 1 of 10 copies -> 90% identity,
        // which sits inside the tool's own 80-97% "degenerate me" band.
        const nCopies=10;
        const varCols=[];
        for(let i=0;i<L;i++) if((i*7+trial)%11===0) varCols.push(i);
        const aligned=[];
        for(let k=0;k<nCopies;k++){
          const a=seq.split('');
          if(k===0){} else if(k===1){ varCols.forEach(c=>{ a[c]='ACGT'[('ACGT'.indexOf(seq[c])+1)%4]; }); }
          aligned.push({label:'s'+k, seq:a.join('')});
        }
        const mask=conservationMaskFromAlignment(aligned);
        const cols=refAlignedCols(aligned[0].seq);
        const conservation={aligned,mask,cols};
        for(const dir of ['F','R']){
          const winStart=10, winLen=22;
          const got=degeneratizePrimerWindow(seq, winStart, winLen, dir, conservation, {maxDeg:2, exclude3:3});
          if(!got) continue;
          const s=got.seq;
          const degIdx=[...s].map((c,i)=>({c,i})).filter(x=>IUP.includes(x.c)).map(x=>x.i);
          results.push({dir, n:degIdx.length, len:s.length,
            minFromThreePrime: degIdx.length?Math.min(...degIdx.map(i=>s.length-1-i)):null,
            reported:got.degeneratePositions.length});
        }
      }
      return results;}""")
    print('windows that gained degenerate bases:', len(out))
    tooMany=[r for r in out if r['n']>2]
    near3=[r for r in out if r['minFromThreePrime'] is not None and r['minFromThreePrime']<3]
    mismatch=[r for r in out if r['n']!=r['reported']]
    byDir={}
    for r in out: byDir[r['dir']]=byDir.get(r['dir'],0)+1
    print('  by direction:', byDir)
    print('  more than 2 ambiguous positions:', len(tooMany), tooMany[:3])
    print('  ambiguous base within 3 of the 3-prime end:', len(near3), near3[:3])
    print('  count disagrees with what the tool reports:', len(mismatch), mismatch[:3])
    print('page errors',errs[:3])
    ctx.close(); b.close()
