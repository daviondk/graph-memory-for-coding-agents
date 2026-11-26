from collections import Counter
import gzip
import json
from pathlib import Path
import numpy as np
d=Path(__file__).resolve().parent
def main():
    records=json.loads(gzip.decompress((d/'traces.json.gz').read_bytes()))
    out={}
    for kind in ('net_count','edge_changed','flag_changed'):
        keys=['groups','any','joint','visits','hits','unique','singletons','repeat_keys','endpoints']
        mat=np.array([[r['metrics'][kind].get(k,0) for k in keys] for r in records])
        totals=mat.sum(axis=0);rng=np.random.default_rng(47107)
        draws=[]
        for _ in range(100):
            it=rng.integers(len(mat),size=(100,len(mat)))
            draws.append(mat[it].sum(axis=1))
        bs=np.concatenate(draws)
        rates={}
        for a,b in [('joint','groups'),('joint','any'),('hits','visits')]:
            l,j=keys.index(a),keys.index(b)
            rate=totals[l]/totals[j]
            ci=np.quantile(bs[:,l]/bs[:,j],[.025,.975])
            rates[a+'/'+b]=[rate,*ci.tolist()]
        out[kind]=dict(totals=dict(zip(keys,totals.tolist())),rates=rates,active_traces=int((mat[:,2]>0).sum()),
                       traces_with_repeat=int((mat[:,4]>0).sum()),max_visits=max(r['metrics'][kind]['max_visits'] for r in records))
    signs=Counter()
    for r in records:signs.update(r['signs'])
    out['signs']=signs
    assert sum(signs.values())==out['net_count']['totals']['visits']
    (d/'results.json').write_text(json.dumps(out,indent=2)+'\n','utf8')
    print(json.dumps(out))
if __name__=='__main__':main()
