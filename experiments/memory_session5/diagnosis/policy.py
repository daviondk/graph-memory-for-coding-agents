"""Reader and writer see only past matrices, six disclosed observations and current test IDs."""
import itertools,math
import numpy as np

def order(scores):return np.argsort(-scores,kind='stable')

def decide(history,pending,probes,observed):
    ids=pending+probes
    table=np.array([[row.get(key,-1) for key in ids] for row in history])
    known=(table>=0).astype(float);failed=(table==1).astype(float)
    age=2**(np.arange(1-len(history),1,dtype=float)/4)
    count=known.sum();overall=(failed.sum()+1)/(count+2)
    static=(age@failed+2*overall)/(age@known+2)
    n=len(pending);quota=math.ceil(.1*n)
    probe_table=table[:,n:]
    adjusted=np.where(probe_table<0,1.,np.where(probe_table==observed,2.,.5))
    cache={}
    def read(packet):
        key=tuple(sorted(packet))
        if key not in cache:
            weight=age.copy()
            if key:weight*=adjusted[:,key].prod(axis=1)
            risks=(weight@failed[:,:n]+2*static[:n])/(weight@known[:,:n]+2)
            cache[key]=risks,order(risks)
        return cache[key]
    def conditional(packet):
        scores=np.empty(n);scores[order(static[:n])]=1/np.arange(1,n+1)
        for i in packet:
            obs=observed[i];mask=(probe_table[:,i]==obs)
            denom=known[mask,:n].sum(axis=0)
            num=(table[mask,:n]==obs).sum(axis=0)
            ratio=np.divide(num,denom,out=np.zeros(n),where=denom>0)
            scores+=.8*(1 if obs else -1)*ratio
        return order(scores)
    common=(5,);full=tuple(range(6))
    out={'static':((),order(static[:n])),'visible':(common,read(common)[1]),'full':(full,read(full)[1]),'conditional-full':(full,conditional(full))}
    surprise=[1-static[n+i] if y else static[n+i] for i,y in enumerate(observed)]
    for b in (1,2):
        choices=list(itertools.combinations(range(5),b))
        def choose(include):
            target=read(full if include else tuple(range(5)))[0]
            suffix=common if include else ()
            return max(choices,key=lambda c:(round(float(target[read(c+suffix)[1][:quota]].sum()),12),c))
        methods={'recent':tuple(range(5-b,5)),'surprise':tuple(sorted(range(5),key=lambda i:(surprise[i],i),reverse=True)[:b]),'aware':choose(True),'blind':choose(False)}
        for name,p in methods.items():
            packet=p+common
            out[f'{name}{b}']=(packet,read(packet)[1])
        recent=methods['recent']+common
        out[f'conditional{b}']=(recent,conditional(recent))
    return {k:{'packet':[probes[i] for i in packet],'rank':[pending[int(j)] for j in rank]} for k,(packet,rank) in out.items()}
