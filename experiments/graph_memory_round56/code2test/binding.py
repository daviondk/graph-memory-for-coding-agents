"""Match per-request historical rank votes by static rank and past test-file frequency."""
import hashlib
import statistics
import numpy as np
from additive import rowsplit
from grade import compare
from source import HERE,read,save,digest

DRAWS=2000
def main():
    rng=np.random.default_rng(56081)
    gold=read(HERE/"ground-truth.json.gz")
    independent=read(HERE/"additive-ranks.json.gz")
    info={};sums={name:np.zeros(DRAWS) for name in ("base","base_pplx")}
    for q,r in rowsplit("code2test"):
        x=r["mats"]["static"];paths=r["paths"]
        mem=r["mats"]["history"][:,-3:];freq=np.rint(np.expm1(r["mats"]["popular"][:,-3])).astype(int)
        hist_rank=sorted(np.flatnonzero(mem[:,0]),key=lambda j:(-mem[j,1],-mem[j,2],paths[j]))[:20]
        graph=np.zeros(len(paths))
        for i,j in enumerate(hist_rank,1):graph[j]=11/(10+i)
        static=x[:,[0,1,3,4,6]].sum(1)
        pos=np.empty(len(paths),int)
        pos[np.argsort(-static,kind="stable")]=np.arange(len(paths))+1
        stratum=np.digitize(pos,[6,21])*4+np.digitize(freq,[1,2,4])
        blocks=[]
        movable=0
        for s in np.unique(stratum[hist_rank]):
            ids=np.flatnonzero(stratum==s)
            vals=graph[ids][graph[ids]>0]
            if len(ids)>1:movable+=len(vals)
            blocks.append((ids,vals))
        # Only 20 static front-runners or a path that can receive a positive vote can enter top-5.
        # For every draw, vectorize over a shortlist of five static rows plus at most twenty voted rows.
        draws={};refs={}
        target=np.array([p in gold[q] for p in paths],float)/len(gold[q])
        picked=[np.empty((DRAWS,0),int),np.empty((DRAWS,0))]
        for ids,vals in blocks:
            if len(ids)==1:
                chosen=np.full((DRAWS,1),ids[0],int)
            else:
                chosen=np.stack([rng.choice(ids,size=len(vals),replace=False) for _ in range(DRAWS)])
            picked[0]=np.concatenate((picked[0],chosen),axis=1)
            picked[1]=np.concatenate((picked[1],np.broadcast_to(vals,(DRAWS,len(vals)))),axis=1)
        for mode,score in (("base",static),("base_pplx",static+x[:,2])):
            orig=np.argsort(-(score+graph),kind="stable")[:5]
            assert [paths[j] for j in orig]==independent[q][mode+"_history"]
            refs[mode]=float(target[orig].sum())
            if len(hist_rank):
                default=np.argsort(-score,kind="stable")[:5]
                source=np.concatenate((np.broadcast_to(default,(DRAWS,5)),picked[0]),axis=1)
                values=np.concatenate((np.broadcast_to(score[default],(DRAWS,5)),score[picked[0]]+picked[1]),axis=1)
                # A voted baseline incumbent also appears in the voted block, so discard its uncopied base slot.
                for i,j in enumerate(default):
                    values[:,i]=np.where((picked[0]==j).any(axis=1),-np.inf,values[:,i])
                rank=np.lexsort((source,-values),axis=1)[:,:5]
                chosen=np.take_along_axis(source,rank,axis=1)
                assert all(len(set(row))==5 for row in chosen[:3])
                rec=target[chosen].sum(axis=1)
            else:rec=np.full(DRAWS,refs[mode])
            draws[mode]=float(rec.mean())
            sums[mode]+=rec
        info[q]={"repo":r["repo"],"votes":len(hist_rank),"movable":movable,"matched_mean":draws,"actual":refs}
    out={"seed":56081,"draws":DRAWS,"votes":sum(r["votes"] for r in info.values()),"movable":sum(r["movable"] for r in info.values()),
         "tasks_with_votes":sum(r["votes"]>0 for r in info.values()),"tasks_with_movable":sum(r["movable"]>0 for r in info.values())}
    for mode,arr in sums.items():
        rows=[{"repo":r["repo"],"metrics":{"actual":[r["actual"][mode]],"matched":[r["matched_mean"][mode]]}} for r in info.values()]
        actual=statistics.fmean(r["actual"][mode] for r in info.values());arr=arr/len(rows)
        out[mode]={"actual":actual,"random_mean":float(arr.mean()),"range95_random":np.quantile(arr,[.025,.975]).tolist(),
                   "probability_match_or_exceed":float((1+(arr>=actual-1e-12).sum())/(DRAWS+1)),
                   "paired":compare(rows,"actual","matched")}
    save(HERE/"binding-events.json.gz",info)
    save(HERE/"binding-results.json",out)
    print(out)
if __name__=="__main__":main()
