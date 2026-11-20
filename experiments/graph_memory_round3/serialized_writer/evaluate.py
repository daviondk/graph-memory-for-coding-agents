"""Grade sealed serialized working memories. Verify every checkpoint size and reproducibility across restarts."""
import gzip,itertools,json,sys
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import writer as w
from writer import HERE,DATA,R2,read,save,rows,h,line
sys.path.insert(0,str(HERE.parent/"context"))
from context import line_target,stream,future
from policy import wordset
ARM=("lru","point","typed","rich_lru")
def shard(k):
    traces=rows(DATA/f"source_{k}.jsonl.gz")
    cp=iter(rows(HERE/f"cuts_{k}.jsonl.gz"));rich=iter(rows(HERE/f"rich_cuts_{k}.jsonl.gz"))
    log=iter(rows(HERE/f"events_{k}.jsonl.gz"));lr=iter(rows(HERE/f"rich_events_{k}.jsonl.gz"))
    costs=defaultdict(list);metrics=[];restarts=0;cuts=0;events=0;verified=0
    weights=(read(R2/"edit_memory/model.json")["flat"],read(R2/"span_memory/width_model.json"),read(R2/"span_memory/offset.json")["intercept"])
    for obj in traces:
        ids=obj["instance"];info={}
        for t,_ in enumerate(obj["events"],1):
            a,ta,logs=next(log);b,tb,rl=next(lr)
            assert (a,ta)==(b,tb)==(ids,t);events+=1
            info[t]={}
            for arm,bc,sha,sz,before,evict,num in logs+rl:
                assert sz<=bc and sz>0;costs[f"{arm}@{bc}"].append((sz,before,evict,num));info[t][arm,bc]=(sha,sz)
        for t,rr,idx,meta,hist,last in stream(obj):
            a,ta,items=next(cp);b,tb,extras=next(rich);assert (ids,t)==(a,ta)==(b,tb);cuts+=1
            req=future(obj["events"],t);target=req if req and req[2] else None
            truth=line_target(rr,target[0],target[1]) if target else None
            gold={};length=0
            if truth:
                path,lo,hi,j=truth;length=hi-lo+1
                gold={q[1]+offset:s for q in rr if q[0]==path for offset,s in enumerate(q[4].split("\n")) if lo<=q[1]+offset<=hi}
                assert len(gold)==length
            scored={}
            for arm,bc,digest,objstate in items+extras:
                blob=w.pack(objstate);sha,size=info[t][arm,bc];assert h(blob)==digest==sha and len(blob)==size<=bc
                when,state,metah,hh,ll=w.materialize(w.payload(blob));assert when==t
                # Verify full encode/decode/encode; the fixed arm metadata fields survive without any hidden object.
                again=w.snapshot(objstate[0],t,state["rebase"],metah,hh,ll,w.pages(state["rebase"]),set())
                assert w.pack(again)==blob;verified+=1
                if arm!="rich_lru" and int(h(f"restart|{ids}|{t}".encode())[:8],16)%37==0:
                    nxt,aux=w.transition(blob,obj["events"][t],{"instance":ids,"issue":obj["issue"]},weights,bc)
                    assert (h(nxt),len(nxt))==info[t+1][arm,bc] and not wordset.cache_info().currsize;restarts+=1
                if target:
                    stored=state["rebase"].get(target[0],{})
                    matches=[stored.get(n,[None])[0]==txt for n,txt in sorted(gold.items())]
                    scored[f"{arm}@{bc}"]=[int(bool(matches) and all(matches)),sum(matches)/max(1,len(matches)),int(bool(matches) and matches[0]),int(len(blob))]
            if target:metrics.append([ids,t,length,scored])
    assert all(next(x,None) is None for x in [cp,rich,log,lr])
    return metrics,costs,{"restarted":restarts,"checked_decodes":verified,"cuts":cuts,"events":events}
def paired(a,b,groups):
    change=np.asarray(a)-np.asarray(b);proj=sorted(set(groups));mask=np.array(groups)
    gs=np.array([change[mask==q].sum(axis=0) for q in proj]);ns=np.array([(mask==q).sum() for q in proj]);g=np.random.default_rng(261118).integers(len(ns),size=(10000,len(ns)))
    stat=gs[g].sum(axis=1)/ns[g].sum(axis=1)[:,None]
    return dict(delta=change.mean(axis=0).tolist(),ci=np.quantile(stat,[.025,.975],axis=0).tolist(),wins=(change>0).sum(axis=0).tolist(),losses=(change<0).sum(axis=0).tolist(),macro=(gs/ns[:,None]).mean(axis=0).tolist())
def main():
    for f in ["checkpoint_lock.json","rich_lock.json"]:
        assert all(h((HERE/n).read_bytes())==s for n,s in read(HERE/f).items())
    with ProcessPoolExecutor(4) as ex:data=list(ex.map(shard,range(8)))
    scored=[r for rs,cs,au in data for r in rs];cc=defaultdict(list);audit=Counter()
    for rs,cs,au in data:
        audit.update(au)
        for a,v in cs.items():cc[a].extend(v)
    with gzip.open(HERE/"scored_steps.jsonl.gz","wt",encoding="utf8",compresslevel=3) as out:
        for r in scored:line(out,r)
    panel=read(DATA/"results.json")["budget"]["512"];assert len(scored)==panel["n"]==1210 and len({r[0] for r in scored})==panel["instances"]
    groups=[r[0].split(".")[0] for r in scored];results={"n":len(scored),"instances":len(set(r[0] for r in scored)),"repos":len(set(groups)),"reachable":sum(r[2]>0 for r in scored),"audit":audit,"arms":{},"comparisons":{}}
    for bc in w.BUDGETS:
        vals={}
        for a in ARM:
            key=f"{a}@{bc}";x=np.array([r[3][key] for r in scored]);vals[a]=x[:,:3]
            costs=np.array(cc[key]);results["arms"][key]={"hits":int(x[:,0].sum()),"fraction":float(x[:,1].mean()),"starts":int(x[:,2].sum()),"max_bytes_all_checkpoints":int(costs[:,0].max()),"mean_bytes_all":float(costs[:,0].mean()),"mean_bytes_at_decision":float(x[:,3].mean()),"evicted_pages":int(costs[:,2].sum()),"events_requiring_eviction":int((costs[:,2]>0).sum()),"mean_encode_calls":float(costs[:,3].mean()),"largest_transient_before_eviction":int(costs[:,1].max())}
        for new,old in [("point","lru"),("typed","lru"),("typed","point"),("rich_lru","lru"),("typed","rich_lru")]:
            results["comparisons"][f"{new}-{old}@{bc}"]=paired(vals[new],vals[old],groups)
    save("results.json",results);print([(a,v["hits"],round(v["fraction"],3)) for a,v in results["arms"].items()],audit,flush=True)
if __name__=="__main__":main()
