"""Learn read-vs-edit demand from prior projects and replay byte-bounded memory on a third cohort."""
import collections,gzip,itertools,json,math,sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
D=Path(__file__).resolve().parent;W=D.parent/"writer"
sys.path.insert(0,str(W))
import optimal
from replay import Memory,old,rows,pages,order,read,save,R2
from optimal import gains,dynamic
from score import locations,stats
from common import printed,rel,success
from policy import DIMS,gen_features
EDITORS={"str_replace_editor","str_replace_based_edit_tool","edit_file"}
ARMS=["lru","edit","read","fixed","adaptive"]
def keyevent(ev):
    name,args,fb=ev
    if name not in EDITORS or not isinstance(args,dict):return "other"
    cmd=args.get("command")
    if cmd=="view":return "view"
    if cmd=="str_replace":return "edit" if success(cmd,args.get("path"),fb) else "failed"
    return "other_editor"
def target(events,t):
    for ev in events[t:t+4]:
        if ev[0] not in EDITORS or not isinstance(ev[1],dict):continue
        kind=keyevent(ev);args=ev[1];p=rel(args.get("path"))
        if not p:return None
        if kind=="edit" and isinstance(args.get("old_str"),str) and args["old_str"]:return kind,p,args["old_str"]
        if kind=="view":
            ls=printed(ev[2])
            if ls:return kind,p,ls
        return None
    return None
def statekey(seq,t):
    return "/".join((seq[-1] if seq else "-",str(seq.count("view")),str(seq.count("edit")),str(t<9)))
def training(k):
    split=old.e.read("split.json");sh=split["shards"][k];ids=set(sh["ids"]);ex=set(split["test"]);kinds=[];reg=[]
    for o in rows(Path(sh["file"])):
        i=o["instance"]
        if i not in ids or i.split(".")[0] in ex:continue
        ids.remove(i);seq=[keyevent(z) for z in o["events"]]
        for t,rr,idx,meta,hist,ls in old.stream(o):
            tar=target(o["events"],t)
            if not tar:continue
            name,path,q=tar;kinds.append((statekey(seq[max(0,t-4):t],t),int(name=="edit")))
            if name!="view":continue
            for j in idx:
                p,a,b,_,body=rr[j]
                val=sum(q.get(z)==ln for z,ln in enumerate(body.split("\n"),a))/len(q) if p==path else 0.
                reg.append((gen_features(rr[j],meta,t,o["issue"]),val))
    return kinds,reg
def fit():
    kinds=[];reg=[]
    with ProcessPoolExecutor(4) as pool:
        for ks,rs in pool.map(training,range(len(old.e.all_files()))):kinds.extend(ks);reg.extend(rs)
    counts=collections.defaultdict(lambda:[0,0]);prior=sum(v for k,v in kinds)/len(kinds)
    for k,v in kinds:counts[k][0]+=v;counts[k][1]+=1
    qr={k:(n+20*prior)/(total+20) for k,(n,total) in counts.items()}
    X=np.array([f for f,v in reg]);y=np.array([v for f,v in reg]);ofs=np.cumsum([0,*DIMS[:-1]]);keys=X+ofs
    coef=np.zeros(sum(DIMS));b=math.log(y.mean()/(1-y.mean()))
    for _ in range(180):
        z=np.clip(b+coef[keys].sum(axis=1),-25,25);err=(1/(1+np.exp(-z))-y)/len(y)
        grad=np.bincount(keys.ravel(),weights=np.repeat(err,len(DIMS)),minlength=len(coef))
        coef-=4*(grad+.0005*coef);b-=4*np.sum(err)
    save(D/"read_model.json",dict(prior=prior,by_state=qr,intercept=b,coef=[coef[a:a+n].tolist() for a,n in zip(ofs,DIMS)],training_windows=len(kinds),read_windows=sum(1-v for k,v in kinds),candidate_rows=len(reg),y_mean=y.mean()))
class Mixed(Memory):
    def __init__(self,model):
        super().__init__();self.par=model;self.last_kinds=[]
    def probability(self,t):return self.par["by_state"].get(statekey(self.last_kinds,t),self.par["prior"])
    def trim(self,rr,cs,t,arm,budget,obj,ew,wm,off):
        if arm=="lru" or sum(cs)<=budget:return super().trim(rr,cs,t,arm,budget,obj,ew,wm,off)
        v=gains(rr,obj,t,self,ew,wm,off);f=np.array([gen_features(r,self.meta,t,obj["issue"]) for r in rr])
        z=self.par["intercept"]+sum(np.take(w,f[:,j]) for j,w in enumerate(self.par["coef"]));pred=1/(1+np.exp(-np.clip(z,-25,25)))
        q={"edit":1.,"read":0.,"fixed":self.par["prior"],"adaptive":self.probability(t)}[arm]
        value=q*v;value[:,0]+=(1-q)*pred
        kept,_=dynamic(cs,value,budget);return set(range(len(rr)))-kept
def project(k):
    ew=read(R2/"edit_memory/model.json")["flat"];wm=read(R2/"span_memory/width_model.json");off=read(R2/"span_memory/offset.json")["intercept"];model=read(D/"read_model.json")
    with gzip.open(D/f"sealed_{k}.jsonl.gz","wt",encoding="utf8") as out:
        for o in rows(D/f"source_{k}.jsonl.gz"):
            policies={a:Mixed(model) for a in [*ARMS,"unbounded"]};cat={};cuts=[]
            for t,event in enumerate(o["events"],1):
                for a,m in policies.items():
                    m.last_kinds=(m.last_kinds+[keyevent(event)])[-4:]
                    m.step(event,t,a,0 if a=="unbounded" else 4096,o,ew,wm,off)
                if t%4 or t>=len(o["events"]):continue
                views={}
                for a,m in policies.items():
                    ids=[]
                    for p,lo,hi,_,body in pages(m.state["rebase"]):
                        key=(p,lo,hi,body)
                        if key not in cat:cat[key]=len(cat)
                        ids.append(cat[key])
                    views[a]=ids
                cuts.append((t,policies["adaptive"].probability(t),views))
            out.write(json.dumps([o["instance"],list(cat),cuts],separators=(",",":"))+"\n")
    return k
def evaluate():
    for n,h in read(D/"prediction_lock.json").items():assert old.e.sha((D/n).read_bytes())==h
    data=[];num=0;model=read(D/"read_model.json")
    for k in range(8):
        src={o["instance"]:o for o in rows(D/f"source_{k}.jsonl.gz")}
        for i,cat,cuts in rows(D/f"sealed_{k}.jsonl.gz"):
            for t,prob,views in cuts:
                num+=1;tar=target(src[i]["events"],t)
                if not tar:continue
                typ,p,goal=tar
                gold=locations([cat[j] for j in views["unbounded"]],p,goal) if typ=="edit" else list(goal.items())
                stats_by={}
                for a,ids in views.items():
                    resident={n:s for j in ids for f,lo,hi,body in [cat[j]] if f==p for n,s in enumerate(body.split("\n"),lo)}
                    frac=sum(resident.get(n)==s for n,s in gold)/len(gold) if gold else 0.
                    stats_by[a]=[float(frac==1) if typ=="edit" else frac,float(frac==1),frac]
                data.append([i,t,typ,prob,stats_by])
    with gzip.open(D/"outcomes.jsonl.gz","wt",encoding="utf8") as out:
        for row in data:out.write(json.dumps(row,separators=(",",":"))+"\n")
    fin={"cuts":num,"groups":{}}
    for label,sub in [("all",data),("edit",[x for x in data if x[2]=="edit"]),("view",[x for x in data if x[2]=="view"])]:
        grp=[x[0].split(".")[0] for x in sub];v={a:np.array([x[-1][a] for x in sub]) for a in [*ARMS,"unbounded"]}
        fin["groups"][label]=dict(n=len(sub),projects=len(set(grp)),scores={a:dict(utility=x[:,0].mean(),whole=int(x[:,1].sum()),frac=x[:,2].mean()) for a,x in v.items()},paired={a:stats(v["adaptive"][:,0],x[:,0],grp) for a,x in v.items() if a!="adaptive"})
    fin["brier"]={k:float(np.mean([(p-int(z[2]=="edit"))**2 for z,p in zip(data,pr)])) for k,pr in {"fixed":[model["prior"]]*len(data),"adaptive":[z[3] for z in data]}.items()}
    save(D/"results.json",fin)
def main():
    deps=[D/"PROTOCOL_RU.md",D/"study.py",D/"acquire.py",D/"selection.json",W/"optimal.py",W/"replay.py",*sorted(D.glob("source_*.gz"))];save(D/"method_lock.json",{str(p):old.e.sha(p.read_bytes()) for p in deps})
    fit()
    with ProcessPoolExecutor(4) as pool:
        for k in pool.map(project,range(8)):print("sealed",k,flush=True)
    files=[D/"method_lock.json",D/"read_model.json",*sorted(D.glob("sealed_*.gz"))]
    save(D/"prediction_lock.json",{p.name:old.e.sha(p.read_bytes()) for p in files});evaluate()
if __name__=="__main__":main()
