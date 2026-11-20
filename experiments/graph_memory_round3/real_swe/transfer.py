"""Only the input dataset and a single fixed 4096-byte limit change. The writer code and weights are unchanged."""
import gzip,hashlib,itertools,json,os,sys,time
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent;S=D.parent/"serialized_writer";sys.path.insert(0,str(S))
import writer as w
sys.path.insert(0,str(D.parent/"context"))
from context import stream,future,line_target
from common import printed,rel
def read(p):return json.loads(Path(p).read_bytes())
def save(n,x):(D/n).write_text(json.dumps(x,ensure_ascii=True,indent=1))
def h(x):return hashlib.sha256(x).hexdigest()
def one(k):
    w.HERE=D;w.DATA=D;w.BUDGETS=(4096,);w.ARMS=("lru","point","typed")
    return w.run(k)
def future_check(events,t):
    for a in events[t:t+4]:
        name,args,obs=a
        if args.get("command")=="str_replace" and rel(args.get("path")) and isinstance(args.get("old_str"),str) and args["old_str"]:
            return args,obs
    return None,None
def verify_anchor(args,obs):
    new=args.get("new_str","")
    if not isinstance(new,str) or not new.strip():return None
    lines=printed(obs);runs=[]
    for n in sorted(lines):
        if not runs or n!=runs[-1][-1]+1:runs.append([])
        runs[-1].append(n)
    pos=[]
    for ns in runs:
        body="\n".join(lines[n] for n in ns);idx=body.find(new)
        while idx>=0:
            pos.append(ns[0]+body[:idx].count("\n"));idx=body.find(new,idx+1)
            if len(pos)>1:return None
    return pos[0] if len(pos)==1 else None
def score(k):
    c=iter(w.rows(D/f"cuts_{k}.jsonl.gz"));logs=iter(w.rows(D/f"events_{k}.jsonl.gz"));au=Counter();cost=defaultdict(list);out=[]
    for obj in w.rows(D/f"source_{k}.jsonl.gz"):
        eu=obj["events"];ids=obj["instance"];stats={}
        for t,evt in enumerate(eu,1):
            i,j,rs=next(logs);assert (i,j)==(ids,t);stats[t]={};au["events"]+=1
            for arm,b,sha,sz,pre,dr,att in rs:
                assert b==4096 and sz<=b;cost[arm].append([sz,pre,dr,att]);stats[t][arm]=(sha,sz)
        for t,rr,idx,mt,hh,ll in stream(obj):
            i,j,packets=next(c);assert (i,j)==(ids,t);au["cuts"]+=1
            q=future(eu,t);req=q if q and q[2] else None;loc=line_target(rr,req[0],req[1]) if req else None
            gold={};check="unlocated" if req else None
            if loc:
                p,lo,hi,_=loc;gold={r[1]+j:s for r in rr if r[0]==p for j,s in enumerate(r[4].split("\n")) if lo<=r[1]+j<=hi}
                assert len(gold)==hi-lo+1
                args,obs=future_check(eu,t);after=verify_anchor(args,obs);check="unverifiable" if after is None else "agrees" if after==lo else "disagrees"
            scores={}
            for arm,b,digest,ss in packets:
                blob=w.pack(ss);assert (h(blob),len(blob))==stats[t][arm] and digest==h(blob)
                ts,state,meta,history,last=w.materialize(ss);assert t==ts
                assert w.pack(w.snapshot(arm,t,state["rebase"],meta,history,last,w.pages(state["rebase"]),set()))==blob
                au["checked_restore"]+=1
                if req:
                    m=state["rebase"].get(req[0],{});matched=[m.get(x,[None])[0]==v for x,v in sorted(gold.items())]
                    scores[arm]=[int(bool(matched) and all(matched)),sum(matched)/max(1,len(matched)),int(bool(matched) and matched[0])]
            if req:out.append([ids,obj["official_repo"],t,len(gold),check,scores])
    assert next(c,None) is None and next(logs,None) is None
    return out,au,cost
def summary(rows):
    if not rows:return {}
    n=len(rows);projects=sorted({r[1] for r in rows});groups=np.array([r[1] for r in rows]);ns=np.array([(groups==q).sum() for q in projects])
    boot=np.random.default_rng(261118).integers(len(ns),size=(10000,len(ns)));vals={k:np.array([r[-1][k] for r in rows]) for k in w.ARMS};res={}
    for new,old in [("typed","point"),("typed","lru"),("point","lru")]:
        diff=vals[new]-vals[old];sums=np.array([diff[groups==q].sum(axis=0) for q in projects]);bs=sums[boot].sum(axis=1)/ns[boot].sum(axis=1)[:,None]
        res[new+"-"+old]=dict(delta=diff.mean(axis=0).tolist(),ci=np.quantile(bs,[.025,.975],axis=0).tolist(),wins=(diff>0).sum(axis=0).tolist(),losses=(diff<0).sum(axis=0).tolist(),macro=(sums/ns[:,None]).mean(axis=0).tolist(),per_repo={q:[int(nn),int(d[0]),float(d[1])] for q,nn,d in zip(projects,ns,sums)})
    return dict(n=n,projects=len(projects),issues=len({r[0] for r in rows}),unique=sum(r[3]>0 for r in rows),post_edit_validation=dict(Counter(r[4] for r in rows)),
       arms={a:dict(hits=int(v[:,0].sum()),fraction=float(v[:,1].mean()),start=int(v[:,2].sum())) for a,v in vals.items()},contrasts=res)
def main():
    phase=sys.argv[1];os.environ["OPENBLAS_NUM_THREADS"]="1"
    if phase=="predict":
        prior=read(S/"method_lock.json");assert all(h(Path(n).read_bytes())==s for n,s in prior.items());assert h((S/"writer.py").read_bytes())==prior[str(S/"writer.py")]
        files=[D/"PROTOCOL_RU.md",D/"choose_issues.py",D/"acquire.py",D/"transfer.py",D/"receipts.json",D/"selection.json",S/"writer.py",S/"method_lock.json",*sorted(D.glob("source_*.gz"))]
        save("method_lock.json",dict(files={str(p):h(p.read_bytes()) for p in files},models={p:s for p,s in prior.items() if p.endswith("model.json") or p.endswith("offset.json")}))
        with ProcessPoolExecutor(4) as pool:times=list(pool.map(one,range(8)))
        save("timings.json",times)
        save("checkpoint_lock.json",{p.name:h(p.read_bytes()) for p in [D/"method_lock.json",*sorted(D.glob("cuts_*.gz")),*sorted(D.glob("events_*.gz"))]})
    if phase=="grade":
        assert all(h((D/n).read_bytes())==s for n,s in read(D/"checkpoint_lock.json").items())
        with ProcessPoolExecutor(4) as pool:data=list(pool.map(score,range(8)))
        rr=[r for results,au,bytes_ in data for r in results];audit=Counter();cc=defaultdict(list)
        for results,au,bytes_ in data:
            audit.update(au)
            for a,v in bytes_.items():cc[a].extend(v)
        with gzip.open(D/"scored.jsonl.gz","wt",encoding="utf8",compresslevel=3) as fp:
            for row in rr:w.line(fp,row)
        # Remove only independently identified source coordinate contradictions as an explicitly reported sensitivity.
        ds=summary(rr);ds.update(audit=dict(audit),storage={a:dict(mean=np.array(v)[:,0].mean(),maximum=int(np.array(v)[:,0].max()),evicted=int(np.array(v)[:,2].sum())) for a,v in cc.items()})
        ds["excluding_observed_coordinate_disagreement"]=summary([r for r in rr if r[4]!="disagrees"])
        ds["independently_localized_subset"]=summary([r for r in rr if r[4]=="agrees"])
        save("results.json",ds)
        print(ds["n"],ds["unique"],ds["arms"],ds["post_edit_validation"])
if __name__=="__main__":main()
