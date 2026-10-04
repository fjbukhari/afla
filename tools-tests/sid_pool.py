"""Species ID multiplex pooling: no two units sharing a pool may conflict by the tool's own test."""
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
      const rnd=(n,seed)=>{let s=seed;const r=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff;};
        return Array.from({length:n},()=>'ACGT'[Math.floor(r()*4)]).join('');};
      const P=getParams();
      const trials=[];
      for(let trial=0; trial<12; trial++){
        const units=[];
        for(let i=0;i<10;i++){
          const seq=rnd(400, trial*101+i*7+3);
          const pairs=primer3Pairs(seq,P);
          if(!pairs.length) continue;
          const p=pairs[0];
          units.push({pairId:'u'+i, target:'t'+i, amplicon:p.ampliconLen,
            oligos:[{seq:p.f.seq,tm:p.f.tm,gc:p.f.gc,type:'primer'},
                    {seq:p.r.seq,tm:p.r.tm,gc:p.r.gc,type:'primer'}],
            tmMin:Math.min(p.f.tm,p.r.tm), tmMax:Math.max(p.f.tm,p.r.tm),
            gcMin:Math.min(p.f.gc,p.r.gc), gcMax:Math.max(p.f.gc,p.r.gc)});
        }
        if(units.length<4) continue;
        const adj=buildConflictGraph(units,'multiplex',P.tmPairDelta!=null?5:5,P.minAmpSep,P.gcSpread);
        const color=dsatur(units.length,adj);
        // every unit must get a pool, and no two conflicting units may share one
        const unassigned=color.filter(c=>c<0).length;
        let violations=0;
        for(let i=0;i<units.length;i++)
          for(const j of adj[i]) if(j>i && color[i]===color[j]) violations++;
        const pools={}; color.forEach(c=>pools[c]=(pools[c]||0)+1);
        trials.push({units:units.length, pools:Object.keys(pools).length,
                     sizes:Object.values(pools), unassigned, violations});
      }
      return trials;}""")
    print(json.dumps(out,indent=1))
    tot=sum(t['violations'] for t in out); un=sum(t['unassigned'] for t in out)
    print(f"\ntrials {len(out)} | conflicting pairs sharing a pool: {tot} | units left unassigned: {un}")
    print('page errors',errs[:3])
    ctx.close(); b.close()
