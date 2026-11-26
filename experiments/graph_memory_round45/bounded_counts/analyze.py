from pathlib import Path
import gzip
import json
import numpy as np

ROOT=Path(__file__).resolve().parent
def main():
    data=json.loads(gzip.decompress((ROOT/'trace-results.json.gz').read_bytes()))
    denominator=np.asarray([r['groups'] for r in data],int)
    names=sorted(data[0]['arms'])
    reads=np.asarray([[r['arms'][n] for n in names] for r in data],int)
    differences=reads[:,::2,0]-reads[:,1::2,0]
    rng=np.random.default_rng(45901)
    boots=[]
    for _ in range(100):
        ix=rng.integers(len(data),size=(100,len(data)))
        boots.append(100*differences[ix].sum(axis=1)/denominator[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(boots),[.025,.975],axis=0)
    groups=int(denominator.sum())
    out={'trajectories':len(data),'groups':groups,'changed_directions':sum(r['changes'] for r in data),'per_arm':{},'eager_minus_deferred_per_100':{}}
    for i,n in enumerate(names):
        out['per_arm'][n]={'reads':int(reads[:,i,0].sum()),'groups_with_read':int(reads[:,i,1].sum())}
    for i,cap in enumerate((1,3,7)):
        dif=differences[:,i]
        out['eager_minus_deferred_per_100'][str(cap)]={'value':100*float(dif.sum())/groups,'ci':ci[:,i].tolist(),'positive_traces':int((dif>0).sum()),'negative_traces':int((dif<0).sum())}
    print(json.dumps(out))
    (ROOT/'results.json').write_text(json.dumps(out,indent=2)+'\n','utf8')
if __name__=='__main__':main()
