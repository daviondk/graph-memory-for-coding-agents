"""Independent offline check. Recreate the winning selection and hot-read LRU, then inspect every published per-request cache."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,gzip
import numpy as np
D=Path(__file__).resolve().parent
def sha(k):return hashlib.sha256((D/k).read_bytes()).hexdigest()
def get(k):
    b=(D/k).read_bytes();return json.loads(gzip.decompress(b) if k.endswith('.gz') else b)
def main():
    s=get('results.json');gd=get('gdsf-results.json');r=get('outcomes.json.gz');g=get('gdsf-outcomes.json.gz');w=get('workload.json.gz');pre=w['pre'];rows=w['rows'];keys={int(k):bytes.fromhex(v) for k,v in get('key-digests.json.gz').items()}
    assert s['program']==sha('admission.py') and s['protocol']==sha('PROTOCOL_RU.md') and s['outcomes']==sha('outcomes.json.gz') and gd['program']==sha('gdsf.py') and gd['rows']==sha('gdsf-outcomes.json.gz') and gd['protocol']==sha('GDSF_PROTOCOL_RU.md')
    parsed={q:{k:z['docs'][str(k)] for k in z['order']} for q,z in rows.items()};count=0
    for q,z in rows.items():
        history=pre[q];now=parsed[q];old=set().union(*(set(parsed[t]) for t in history))
        for budget,b in s['budgets'].items():
            cap=b['slots'];hist_lru=[];weighted={};counts=Counter();steps=0
            for t in history:
                docs=parsed[t];hits=hist_lru.copy();ordering=[i for i in docs if i not in hits]+[i for i in docs if i in hits]
                for i in ordering:
                    if i in hist_lru:hist_lru.remove(i)
                    hist_lru=(hist_lru+[i])[-cap:]
                for i in docs:
                    if steps and steps%1024==0:
                        counts=Counter({k:v//2 for k,v in counts.items()})
                    steps+=1
                    for j,idx in enumerate(keys[i][:4]):
                        loc=(j,idx);counts[loc]=min(255,counts[loc]+1)
                pool=dict(weighted,**{})|docs
                score={i:n*(1+min(counts[j,x] for j,x in enumerate(keys[i][:4]))) for i,n in pool.items()}
                weighted={i:pool[i] for i in sorted(pool,key=lambda i:(-score[i],keys[i]))[:cap]}
            data=r[q]['caps'][budget]
            assert list(weighted)==data['proposed']['cache'] and hist_lru==data['hot_lru']['cache']
            for arm,v in data.items():
                if arm=='oracle':cs=sorted(old&now.keys(),key=lambda k:(-now[k],keys[k]))[:cap]
                else:
                    cs=v['cache'];assert len(cs)<=cap and len(set(cs))==len(cs) and set(cs)<=old
                    assert v['packed_metadata']==256+1024+len(cs)*64 and v['packed_metadata']+len(cs)*16384<=b['bytes']
                assert sum(now[k] for k in now if k in cs)==v['saved'] and len(now.keys()&set(cs))==v['hits'];count+=1
            for mode,v in g[q][budget].items():
                cs=set(v['prior']);assert len(cs)<=cap and cs<=old and sum(now[k] for k in now if k in cs)==v['saved'] and len(now.keys()&cs)==v['hits'];count+=1
    ids=sorted({v['repo'] for v in r.values()});den=np.array([sum(v['tokens'] for v in r.values() if v['repo']==k) for k in ids]);weights=np.random.default_rng(480532).multinomial(len(ids),np.repeat(1/len(ids),len(ids)),size=20000)
    for competitor in ['hot_lru','batch']:
        dr=np.array([sum(z['caps']['512']['proposed']['saved']-(g[q]['512']['batch']['saved'] if competitor=='batch' else z['caps']['512']['hot_lru']['saved']) for q,z in r.items() if z['repo']==k) for k in ids])
        c=np.quantile((weights@dr)/(weights@den),[.025,.975])
        target=gd['panels']['512']['both']['batch'] if competitor=='batch' else s['panels']['512']['both']['contrasts']['proposed minus hot_lru']
        assert np.allclose(target['ci'],c) and np.isclose(target['delta'],dr.sum()/den.sum())
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in get('manifest.json')['files'].items())
    print('Verified',count,'policy/state/capacity outcomes, serialized sizes, complete eligible histories, primary/new policy from scratch, and both highlighted cluster intervals.')
if __name__=='__main__':main()

