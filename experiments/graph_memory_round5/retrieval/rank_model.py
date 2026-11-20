from conditional import *
from common5 import *
from target_io import target_rows

def transform(orders,case):
    r=positions(orders);basic=basis(r);g,o,l=r.T;rec=1/r
    p=(g-np.minimum(o,l))/np.maximum(1,np.minimum(o,l))
    features=[np.minimum(p,3),np.maximum(0,1/g-1/o)*rec[:,2],(1/o-1/g)*rec[:,2],(1/g-1/o)*(l<=3)]
    for i,j in ((0,1),(0,2),(1,2)):
        a,b=rec[:,i],rec[:,j]
        features.extend([a*b,np.minimum(a,b),abs(a-b),((a>=.5)&(b>=.5)).astype(float),a*(r[:,j]<=3),b*(r[:,i]<=3)])
    # Test whether graph promotions deserve different confidence when experts disagree.
    for i in range(3):
        for j,k in ((0,1),(0,2),(1,2)):
            features.append(rec[:,i]*float(orders[j][0]==orders[k][0]))
    extra=np.column_stack(features);ling=r[:,1:]
    return {'linear':np.column_stack([1/r,(len(r)-r)/max(1,len(r)-1),r==1]),'additive':basic,'adaptive':np.column_stack([basic,extra]),'placebo':np.column_stack([basic,shuffled(extra,case)]),'without_graph':np.column_stack([basis(ling),rec[:,1]*rec[:,2],np.minimum(rec[:,1],rec[:,2]),rec[:,1]*(ling[:,1]<=3),rec[:,2]*(ling[:,0]<=3)])}
def inputs(path):
    for panel,j,repo,h,rank in rr(path):
        yield (panel,j,repo,[rank[k] for k in ('graph','owner','jaccard')])
def labels(path):
    return {(a,int(j)):int(y) for a,j,y,*_ in rr(path)}
def main():
    # Only the development label file is opened in this program.
    dev=list(inputs(R/'full.pred.jsonl.gz'));val=list(inputs(R/'archive.pred.jsonl.gz'))
    assert not {r[2] for r in dev}&{r[2] for r in val}
    paths=sorted((R/'inputs').glob('java_*_test_*.parquet'));y=dict(target_rows(paths));ys=[y[a,j][1] for a,j,_,_ in dev]
    assert len(set(ys))>5 and all(y[a,j][0]==p and 0<=y[a,j][1]<len(o[0]) for a,j,p,o in dev)
    ref={(a,j):v for a,j,_,p,n,b,v in rr(R/'full.scores.jsonl.gz')}
    assert all(ref[a,j]['graph'][3] == 1/(o[0].index(y[a,j][1])+1) for a,j,p,o in dev)
    sizes=[len(o[0]) for a,j,p,o in dev]
    lockpaths=[D/f for f in ('PROTOCOL_RU.md','conditional.py','rank_model.py')]+[D/'target_io.py']+paths+[R/f for f in ('full.pred.jsonl.gz','full.scores.jsonl.gz','archive.pred.jsonl.gz')]
    dump('ranking_lock.json',dict(utc=now(),hashes={str(p.name):filehash(p) for p in lockpaths},train_n=len(dev),test_n=len(val),l2=.0005))
    # Preallocate to keep total local memory bounded, materialize independent arms sequentially.
    names=('linear','additive','adaptive','placebo','without_graph')
    def matrix(data,names):
        sizes=[len(o[0]) for _,_,_,o in data];total=sum(sizes);out={};offset=0
        for panel,j,p,o in data:
            f=transform(o,panel+'|'+str(j))
            if not out:out={k:np.zeros((total,len(f[k][0])),dtype=np.float32) for k in names}
            for k in names:out[k][offset:offset+len(o[0])]=f[k]
            offset+=len(o[0])
        return out
    data=matrix(dev,names);models={}
    for k in names:
        models[k]=fit(data.pop(k),sizes,ys,.0005)
    dump('rank_weights.json',models)
    def predictions():
        for panel,j,p,o in val:
            f=transform(o,panel+'|'+str(j));r=positions(o)
            methods={k:ordered(f[k]@np.asarray(v['weights'])) for k,v in models.items()}
            methods.update(graph=o[0],owner=o[1],jaccard=o[2],rrf=ordered(np.sum(1/(60+r),axis=1)))
            yield dict(panel=panel,idx=j,project=p,query=3,orders=methods)
    jsonrows('rank_predictions.jsonl.gz',predictions())
    dump('rank_decisions.json',dict(utc=now(),rows=len(val),pred=filehash(D/'rank_predictions.jsonl.gz'),weights=filehash(D/'rank_weights.json')))
if __name__=='__main__':main()

