"""Replay one phase. Holdout predictions are sealed before gold or model calibration is read."""
import math,os,time,json,gzip,hashlib,sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import Counter,defaultdict
import itertools
import numpy as np
from shared import D,A,B,R3,WORK,read,save,sha,rows,write,stream,future,line_target,prior
from memory import METHODS,CANDIDATES,CONTROLS,transition,initial,pack,unpack
from transfer_followup import verify_anchor,future_check

def config(panel):
    return {"A":A,"B":B,"C":D}[panel],D/("panel_"+panel)
def weights():
    return (read(prior.R2/"edit_memory/model.json")["flat"],read(prior.R2/"span_memory/width_model.json"),
            read(prior.R2/"span_memory/offset.json")["intercept"])

def predict(inputs):
    panel,k,arms=inputs;src,out=config(panel);ws=weights();times=Counter();elapsed=time.monotonic()
    with gzip.open(out/f"cuts_{k}.gz","wt",encoding="utf8",compresslevel=2) as cf,gzip.open(out/f"events_{k}.gz","wt",encoding="utf8",compresslevel=2) as ef:
        for obj in rows(src/f"source_{k}.jsonl.gz"):
            iid=obj["instance"];static=dict(instance=iid,issue=obj["issue"]);states={a:initial(a) for a in arms}
            for t,event in enumerate(obj["events"],1):
                cut=(t%4==0 and t<len(obj["events"]));packets={};metrics={}
                for method,old in states.items():
                    tick=time.perf_counter_ns();new,fit=transition(method,old,event,static,ws);delta=time.perf_counter_ns()-tick
                    times[method]+=delta;states[method]=new
                    digest=hashlib.sha256(new).hexdigest()
                    metrics[method]=[digest,*fit,delta]
                    if cut:
                        use_dict=METHODS[method][1];v=unpack(new,use_dict)
                        assert pack(v,use_dict)==new and v[1]==t
                        packets[method]=v
                write(ef,[iid,t,metrics])
                if cut:write(cf,[iid,t,packets])
    return dict(k=k,elapsed=time.monotonic()-elapsed,ns=times)

def evaluate_shard(inputs):
    panel,k,arms=inputs;src,out=config(panel)
    cuts=iter(rows(out/f"cuts_{k}.gz"));events=iter(rows(out/f"events_{k}.gz"))
    outrows=[];cost=defaultdict(list);aud=Counter()
    for task in rows(src/f"source_{k}.jsonl.gz"):
        iid=task["instance"];digests={}
        for i in range(1,len(task["events"])+1):
            id_,time,metrics=next(events);assert (id_,time)==(iid,i)
            digests[i]={k:(v[0],v[2]) for k,v in metrics.items()}
            for a,(h,b,sz,drop,trials,dt) in metrics.items():
                assert 0<sz<=4096;aud["byte_checks"]+=1;cost[a].append((sz,dt,b>4096,drop,trials))
        for t,rr,idx,meta,hist,last in stream(task):
            id_,time,states=next(cuts);assert (id_,time)==(iid,t)
            query=future(task["events"],t);query=query if query and query[2] else None
            loc=line_target(rr,query[0],query[1]) if query else None
            lines={};check="unlocated" if query else ""
            if loc:
                path,lo,hi,j=loc
                lines={r[1]+h:line for r in rr if r[0]==path for h,line in enumerate(r[4].split("\n")) if lo<=r[1]+h<=hi}
                assert len(lines)==hi-lo+1
                arg,obs=future_check(task["events"],t)
                anchor=verify_anchor(arg,obs);check="no_anchor" if anchor is None else "agrees" if anchor==lo else "disagrees"
            scores={}
            for a,state in states.items():
                codec=METHODS[a][1];blob=pack(state,codec)
                assert (hashlib.sha256(blob).hexdigest(),len(blob))==digests[t][a]
                ts,stored,memory_meta,history,last_edit=prior.materialize(state);memory=stored["rebase"]
                recoded=prior.snapshot(state[0],ts,memory,memory_meta,history,last_edit,prior.pages(memory),set())
                assert ts==t and pack(recoded,codec)==blob;aud["decodes"]+=1
                if query:
                    file_mem=memory.get(query[0],{})
                    match=[file_mem.get(n,[None])[0]==v for n,v in sorted(lines.items())]
                    scores[a]=[int(bool(match) and all(match)),sum(match)/max(1,len(match)),int(bool(match) and match[0])]
            if query:outrows.append([iid,task["official_repo"],t,len(lines),check,scores])
    assert next(cuts,None) is None and next(events,None) is None
    return outrows,cost,aud

def paired(rows,new,old):
    groups=[r[1] for r in rows];gid=sorted(set(groups));issue=sorted({r[0] for r in rows})
    d=np.array([r[-1][new][0]-r[-1][old][0] for r in rows],int)
    tot=Counter();tot_i=Counter();ni=Counter();n=Counter()
    for row,delta in zip(rows,d):
        i,g=row[:2];tot[g]+=int(delta);tot_i[i]+=int(delta);n[g]+=1;ni[i]+=1
    rng=np.random.default_rng(41826)
    blocks=np.array([[tot[g],n[g]] for g in gid]);boot=blocks[rng.integers(len(gid),size=(10000,len(gid)))].sum(axis=1)
    strat=np.zeros((10000,2),int)
    for g in gid:
        ids={r[0] for r in rows if r[1]==g};m=np.array([[tot_i[i],ni[i]] for i in sorted(ids)])
        strat+=m[rng.integers(len(m),size=(10000,len(m)))].sum(axis=1)
    phit=d.mean();q=lambda ar:np.quantile(ar[:,0]/ar[:,1],[.025,.975]).tolist()
    cnt=0
    for signs in itertools.product((-1,1),repeat=len(gid)):
        if abs(sum(x*tot[g] for x,g in zip(signs,gid)))>=abs(int(d.sum())):cnt+=1
    return dict(delta=float(phit),net=int(d.sum()),wins=int((d>0).sum()),losses=int((d<0).sum()),
                mean_issue=float(np.mean([tot_i[i]/ni[i] for i in issue])),mean_repo=float(np.mean([tot[g]/n[g] for g in gid])),
                ci_issues_within_repos=q(strat),ci_repos=q(boot),per_repo={g:[tot[g],n[g]] for g in gid},signflip_repo=cnt/2**len(gid))

def main():
    phase,panel=sys.argv[1:3];src,out=config(panel);out.mkdir(exist_ok=True)
    arms=list(METHODS) if panel!="C" else read(D/"freeze.json")["arms"]
    if panel=="C":
        assert all(sha(Path(n))==v for n,v in read(D/"freeze.json")["inputs"].items())
    if phase=="predict":
        assert not (out/"checkpoint_lock.json").exists(),"use a fresh destination to retain sealed predictions"
        with ProcessPoolExecutor(4) as pool:timing=list(pool.map(predict,[(panel,k,arms) for k in range(8)]))
        save(out/"times.json",timing)
        save(out/"checkpoint_lock.json",{p.name:sha(p) for p in sorted(out.glob("*.gz"))})
        print("sealed",panel,flush=True)
    elif phase=="grade":
        assert all(sha(out/n)==v for n,v in read(out/"checkpoint_lock.json").items())
        with ProcessPoolExecutor(4) as pool:parts=list(pool.map(evaluate_shard,[(panel,k,arms) for k in range(8)]))
        rs=[];costs=defaultdict(list);audit=Counter()
        for subset,cost,au in parts:
            rs.extend(subset);audit.update(au)
            for a,li in cost.items():costs[a].extend(li)
        with gzip.open(out/"scored.jsonl.gz","wt",encoding="utf8") as f:
            for r in rs:write(f,r)
        stats={};op={}
        for a in arms:
            arr=np.array([r[-1][a] for r in rs]);cost=np.array(costs[a])
            stats[a]=dict(full=int(arr[:,0].sum()),fraction=float(arr[:,1].mean()),start=int(arr[:,2].sum()))
            op[a]=dict(mean_bytes=float(cost[:,0].mean()),max_bytes=int(cost[:,0].max()),mean_ms=float(cost[:,1].mean()/1e6),
                       median_ms=float(np.median(cost[:,1])/1e6),p95_ms=float(np.quantile(cost[:,1],.95)/1e6),overflows=int(cost[:,2].sum()),
                       mean_compressions=float(cost[:,4].mean()))
        candidates=([read(D/"freeze.json")["candidate"]] if panel=="C" else CANDIDATES)
        pairs={f"{new}-{old}":paired(rs,new,old) for new in candidates for old in CONTROLS if old!=new and old in arms}
        save(out/"results.json",dict(n=len(rs),issues=len({r[0] for r in rs}),repos=sorted({r[1] for r in rs}),
             anchor=Counter(r[4] for r in rs),reachable=sum(r[3]>0 for r in rs),arms=stats,operation_cost=op,checks=audit,comparisons=pairs))
        print(panel,len(rs),{k:v["full"] for k,v in stats.items()},flush=True)
    else:raise ValueError(phase)
if __name__=="__main__":main()
