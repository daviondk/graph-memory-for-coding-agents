"""Join author-native Coverage@1024 per query to the native semantic labels."""
from collections import defaultdict
import numpy as np
import modes as s

def main():
    src=s.SERIES/'factor_reader'
    d=s.read(src/'metrics-test-rows.json.gz')
    h=s.read(src/'metrics-hash64-rows.json.gz')
    primary={r['q']:r for r in s.read(s.HERE/'factor_hash64-data.json.gz')}
    assert len(primary)==2000 and set(primary)==set(d['dense'])==set(d['degree'])==set(h['rgcn'])
    rows={}
    for q,r in primary.items():
        assert all(r['t']==group[q]['t'] for group in [d['dense'],d['degree'],h['rgcn']])
        rows[q]={'t':r['t'],'mode':r['mode'],'degree':d['degree'][q]['coverage_1024'],
                 'dense':d['dense'][q]['coverage_1024'],'rgcn_hash64':h['rgcn'][q]['coverage_1024']}
    mods=['dense','degree','rgcn_hash64']
    grouped=defaultdict(lambda:np.zeros((3,4)))
    for r in rows.values():
        grouped[r['t']][s.ORDER.index(r['mode'])] += [1.,*[r[n] for n in mods]]
    mat=np.stack([grouped[t] for t in sorted(grouped)])
    summed=mat.sum(axis=0)
    pt=summed[:,1:]/summed[:,:1]
    rng=np.random.default_rng(13);sims=[]
    for i in range(0,10000,64):
        ix=rng.integers(0,len(mat),(min(10000-i,64),len(mat)));v=mat[ix].sum(axis=1)
        sims.append(v[:,:,1:]/v[:,:,:1])
    samples=np.concatenate(sims)
    out={}
    for i,mode in enumerate(s.ORDER):
        dif=samples[:,i,1]-samples[:,i,0]
        out[mode]={'methods':dict(zip(mods,pt[i].tolist(),strict=True)),
                   'degree_minus_dense':{'estimate':float(pt[i,1]-pt[i,0]),'ci95':np.quantile(dif,[.025,.975]).tolist()}}
    s.put(s.HERE/'coverage-1024.json',dict(protocol=s.h(s.HERE/'plan.json'),code=s.h(s.HERE/'coverage.py'),rows_test=s.h(src/'metrics-test-rows.json.gz'),
          rows_hash=s.h(src/'metrics-hash64-rows.json.gz'),groups=out))
    print(out)

if __name__=='__main__':
    main()
