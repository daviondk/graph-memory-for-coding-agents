"""Within-trajectory intervals for the registered locality and hardware-cycle controls."""
from analyze import D,read,sha,np
import argparse,json
def calculate():
    base=read(D/'cycles-seal.json');reg=read(D/'interleave-registration.json');assert base['registration']==sha(D/'interleave-registration.json') and reg['prior']==sha(D/'results.json')
    names=reg['arms'];pairs=[('scan','scan_memo'),('scan','deferred'),('scan_memo','deferred_memo'),('eager','deferred'),('exact','deferred'),('exact_memo','scan_memo')]
    x=[names.index(a) for a,b in pairs];y=[names.index(b) for a,b in pairs];output={}
    for mode in ['serial','interleaved']:
        data=[]
        for rep in range(3):
            p=D/f'cycle-{rep}-{mode}.json.gz';assert sha(p)==base['runs'][p.name]
            rows=read(p);data.append(np.array([rows[n] for n in names],dtype='int64'))
        z=np.array(data).sum(0);flat=z[:,:,:2].transpose(1,0,2).reshape(1207,-1);summed=z.sum(1);rng=np.random.default_rng(460131)
        sample=[]
        for _ in range(100):
            w=rng.multinomial(1207,np.full(1207,1/1207),size=100);a=(w@flat).reshape(100,len(names),2);sample.append(a[:,x,:]/a[:,y,:])
        lo,hi=np.quantile(np.concatenate(sample),[.025,.975],axis=0);point=summed[x,:2]/summed[y,:2]
        ratios={a+'/'+b:{m:[point[i,j],lo[i,j],hi[i,j]] for j,m in enumerate(('wall','cycles'))} for i,(a,b) in enumerate(pairs)}
        output[mode]={'ratios':ratios,'per_pass':{n:(v/3).tolist() for n,v in zip(names,summed)}}
    return output
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');o=p.parse_args()
    r=calculate();out=D/'cycle-results.json'
    if o.write and not out.exists():out.write_bytes((json.dumps(r,sort_keys=True,indent=2)+'\n').encode())
    assert r==read(out);print('Recomputed secondary wall and thread-cycle ratios.')

