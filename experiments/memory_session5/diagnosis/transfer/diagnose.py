"""Post-result falsification by a three-subset static surprise compressor."""
import gzip,json,sys
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
from run import collect,ROOT
def diagnostics():
    sessions=collect()
    lookup={(mode,s,i):(st,ys) for (mode,s),rs in sessions.items() for st,en,i,ys in rs}
    rows=defaultdict(list)
    for line in gzip.decompress((ROOT/'outputs.jsonl.gz').read_bytes()).splitlines():
        r=json.loads(line);ms=r['methods'];mode,s,i=r['setting'],r['system'],r['id']
        st,ys=lookup[mode,s,i];positives=sum(ys.values())-sum(v for _,v in r['probes'])
        for base,arm in [('surprise','cheap_minimal'),('recent','cheap_recent')]:
            target=set(ms[base+'2']['chosen'])
            md=next(ms[base+str(q)] for q in (0,1,2) if set(ms[base+str(q)]['chosen'])==target)
            ms[arm]=md
        for a,md in ms.items():
            hits=sum(ys[t] for t in md['chosen'])
            rows[mode,s,a].append((st//(14*86400),hits,positives,(len(bytes.fromhex(md['packet']))-1)//3,len(md['chosen'])))
    out={}
    for mode in ('BN','MI'):
        systems=sorted({s for m,s,k in rows if m==mode})
        methods=sorted({k for m,s,k in rows if m==mode})
        totals={}
        for arm in methods:
            rs=[r for s in systems for r in rows[mode,s,arm]]
            recalls=[np.mean([h/f for d,h,f,b,k in rows[mode,s,arm] if f]) for s in systems if any(r[2] for r in rows[mode,s,arm])]
            totals[arm]={'records':sum(r[3] for r in rs),'bytes':sum(1+3*r[3] for r in rs),'sessions':len(rs),'eligible':sum(r[2]>0 for r in rs),'failures':sum(r[2] for r in rs),'detected':sum(r[1] for r in rs),'selections':sum(r[4] for r in rs),'macro_recall':float(np.mean(recalls)),'length':dict(Counter(r[3] for r in rs))}
        contrasts={}
        for base in ['fixed','zero','full','matched_recent','matched_surprise','oracle_len_surprise','cheap_minimal','surprise2']:
            ds=[];blocks=defaultdict(list)
            for sys in systems:
                av=[]
                for a,b in zip(rows[mode,sys,'minimal'],rows[mode,sys,base]):
                    assert a[0]==b[0] and a[2]==b[2]
                    if a[2]:
                        d=(a[1]-b[1])/a[2];av.append(d);blocks[a[0]].append(d)
                if av:ds.append(np.mean(av))
            rng=np.random.default_rng(17112026)
            sims=np.mean(rng.choice(ds,(10000,len(ds)),replace=True),axis=1)
            vals=list(blocks.values()); ix=rng.integers(0,len(vals),size=(10000,len(vals)))
            sv=np.array([sum(v) for v in vals]);nv=np.array([len(v) for v in vals]);bt=sv[ix].sum(axis=1)/nv[ix].sum(axis=1)
            contrasts[base]={'macro_delta':float(np.mean(ds)),'system_bootstrap_interval':np.quantile(sims,[.025,.975]).tolist(),'pooled_session_delta':sv.sum()/nv.sum(),'synchronized_14d_block_pooled_interval':np.quantile(bt,[.025,.975]).tolist(),'blocks':len(vals),'systems_in_estimand':len(ds)}
        out[mode]={'methods':totals,'minimal_minus':contrasts}
    return out
if __name__=='__main__':
    d=diagnostics();(ROOT/'analysis.json').write_text(json.dumps(d,indent=1))
    for m,x in d.items():
        print(m, {a:x['methods'][a] for a in ('minimal','cheap_minimal','matched_surprise')},x['minimal_minus']['matched_surprise'],x['minimal_minus']['cheap_minimal'])
