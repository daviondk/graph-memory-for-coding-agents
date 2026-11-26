import gzip
import json
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent
def main():
    raw=json.loads(gzip.decompress((root/'control-times.json.gz').read_bytes()))
    sizes=json.loads((root/'view-log.json').read_bytes())
    arms=['direct','sql','ram','memo']
    out={}
    for scenario in ('new','repeated'):
        rows=[r for r in raw if r[0]==scenario]
        qs=sorted(sizes['queries'])
        s=np.zeros((len(qs),len(arms)),dtype=np.float64)
        counts=np.zeros_like(s)
        for _,_,q,arm,n,t in rows:
            i,j=qs.index(q),arms.index(arm)
            counts[i,j]+=n
            s[i,j]+=t
        assert np.all(counts==counts[:,[0]])
        rng=np.random.default_rng(46461)
        sample=rng.integers(len(qs),size=(10000,len(qs)))
        b=s[sample].sum(axis=1);tot=s.sum(axis=0);per=s.sum(axis=0)/counts.sum(axis=0)
        out[scenario]={'mean_us':dict(zip(arms,(per/1000).tolist())),'per_mode':int(counts[:,0].sum()),'ratios':{}}
        for j,k in ((0,1),(0,3),(1,2),(3,1),(1,3)):
            out[scenario]['ratios'][arms[j]+'/'+arms[k]]=[tot[j]/tot[k],*np.quantile(b[:,j]/b[:,k],[.025,.975]).tolist()]
        out[scenario]['build_break_even_vs_direct']=int(np.ceil(sizes['build_ns']/(per[0]-per[1]))) if per[0]>per[1] else None
    (root/'control-results.json').write_text(json.dumps(out,indent=2)+'\n','utf8')
    print(json.dumps(out))
if __name__=='__main__':main()
