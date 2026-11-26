"""Effect of actually removing the duplicate flag bits, three complete disk-based repeats."""
from analyze import D,read,sha,np
import argparse,json
def calculate():
    registration=read(D/'compact-registration.json');arms=registration['arms'];rows=[];files={}
    r45=read(D/'inputs/r45-per-trace.json.gz')
    for rep in range(3):
        p=D/f'dense-{rep}.json.gz';obs=read(p);files[p.name]=sha(p);states=obs['traces']
        for a in ('dense_sql','dense_lut','deferred'):assert [v[1] for v in states[a]]==[v['arms']['3-1'][0] for v in r45]
        rows.append([np.asarray(states[a])[:,0] for a in arms])
    times=np.array(rows).sum(0).T
    keys=[('deferred','dense_sql'),('deferred','dense_lut'),('exact','dense_sql'),('scan','dense_sql'),('scan','dense_lut')]
    x=[arms.index(a) for a,b in keys];y=[arms.index(b) for a,b in keys];s=times.sum(0);rng=np.random.default_rng(460131);boots=[]
    for _ in range(100):
        w=rng.multinomial(1207,np.full(1207,1/1207),size=100);v=w@times
        boots.append(v[:,x]/v[:,y])
    lo,hi=np.quantile(np.concatenate(boots),[.025,.975],axis=0)
    return {'files':files,'ms_per_pass':dict(zip(arms,(s/3e6).tolist())),'pages_bytes':{a:obs['physical'][a]['file'] for a in arms},
            'objects':{a:obs['physical'][a]['objects'] for a in arms},'ratios':{a+'/'+b:[s[x[j]]/s[y[j]],lo[j],hi[j]] for j,(a,b) in enumerate(keys)}}
if __name__=='__main__':
    op=argparse.ArgumentParser();op.add_argument('--write',action='store_true');args=op.parse_args()
    z=calculate();dest=D/'compact-results.json'
    if args.write and not dest.exists():dest.write_bytes((json.dumps(z,sort_keys=True,indent=2)+'\n').encode())
    assert read(dest)==z

