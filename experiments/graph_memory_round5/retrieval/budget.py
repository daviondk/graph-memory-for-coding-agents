"""Feature-only allocation, immutable graph order, equal allowance in every microbatch."""
from rank_model import transform,inputs
from target_io import target_rows
from conditional import *
from common5 import *
from collections import Counter,defaultdict
import heapq
def pool(n):return 0 if n<=10 else 1
def base(r):
    rank=r[:,None].astype(float);n=len(r)
    return np.c_[basis(rank),basis(rank)*np.log(n),basis(rank)*pool(n)]
def soft(z):
    z=np.exp(z-z.max());return z/z.sum()
def monotone(x):
    levels=[];counts=[]
    for v in x:
        levels.append(v);counts.append(1)
        while len(levels)>=2 and levels[-2]<levels[-1]:
            a,b=counts[-2:];c,d=levels[-2:]
            levels[-2:]=[(c*a+d*b)/(a+b)];counts[-2:]=[a+b]
    return np.repeat(levels,counts)
def main():
    dev=list(inputs(R/'full.pred.jsonl.gz'));test=list(inputs(R/'archive.pred.jsonl.gz'))
    gold=dict(target_rows((R/'inputs').glob('java_*_test_*.parquet')))
    ys=[];sizes=[];xx=[];counts=defaultdict(Counter);coarse=defaultdict(Counter);old=load(D/'rank_weights.json')
    for panel,j,repo,o in dev:
        y=gold[panel,j][1];n=len(o[0]);r=positions([o[0]])[:,0];place=int(r[y]);ys.append(y);sizes.append(n);xx.append(base(r))
        counts[n][place]+=1;coarse[pool(n)][place]+=1
    m=fit(np.vstack(xx),sizes,ys,.0005)
    dump('budget_model.json',dict(utc=now(),base=m,counts={str(k):dict(v) for k,v in counts.items()},coarse={str(k):dict(v) for k,v in coarse.items()},old=filehash(D/'rank_weights.json'),plan=filehash(D/'BUDGET_PROTOCOL_RU.md'),file=filehash(D/'budget.py')))
    preds={};limits={};methods=('empirical','count_model','linear','additive','adaptive')
    for panel,j,repo,o in test:
        key=panel,j;n=len(o[0]);r=positions([o[0]])[:,0];f=transform(o,panel+'|'+str(j));cut=min(n,8);limits[key]=cut
        empirical=np.array([counts[n][pos]+100*(coarse[pool(n)][pos]+.5)/(sum(coarse[pool(n)].values())+.5*n) for pos in range(1,n+1)])
        dd={'empirical':empirical/empirical.sum(),'count_model':soft(base(r)@m['weights'])[o[0]]}
        for arm in ('linear','additive','adaptive'):dd[arm]=soft(f[arm]@old[arm]['weights'])[o[0]]
        preds[key]={a:monotone(v[:cut]) for a,v in dd.items()}
    order=sorted(preds,key=lambda x:sha('budget5|'+x[0]+'|'+str(x[1])));out=[]
    for k in (2,3,5):
        for off in range(0,len(order),32):
            group=order[off:off+32]
            rows=[dict(panel=p,idx=j,allowance=k,block=off//32,depth={'fixed':min(k,limits[p,j])}) for p,j in group]
            budget=sum(row['depth']['fixed'] for row in rows)
            for arm in methods:
                heap=[(-preds[key][arm][1],i,2) for i,key in enumerate(group) if limits[key]>=2];heapq.heapify(heap);depth=[1]*len(group)
                for _ in range(budget-len(group)):
                    _,i,l=heapq.heappop(heap);depth[i]=l;key=group[i]
                    if l<limits[key]:heapq.heappush(heap,(-preds[key][arm][l],i,l+1))
                assert sum(depth)==budget
                for i,row in enumerate(rows):row['depth'][arm]=depth[i]
            out.extend(rows)
    jsonrows('budget_predictions.jsonl.gz',out);dump('budget_lock.json',dict(utc=now(),rows=len(out),pred=filehash(D/'budget_predictions.jsonl.gz'),model=filehash(D/'budget_model.json')))
if __name__=='__main__':main()

