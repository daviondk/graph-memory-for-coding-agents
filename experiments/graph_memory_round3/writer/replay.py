"""Replay only observed editor events, keep separate bounded stores and seal resident pages before scoring."""
import gzip,heapq,json,sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent;DATA=D.parent/"context";R2=D.parent.parent/"graph_memory_round2"
sys.path.insert(0,str(R2/"span_memory"))
import run as old
from experiment import write_event
from common import newmeta,pages,advance,rel,success,rows
from policy import order
ARMS=("lru","twice","point","global","typed","placebo");BUDGETS=(4096,12288)
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=True,indent=1),encoding="utf8")
def read(p):return json.loads(p.read_bytes())
def cost(r):return len((f"@@ {r[0]} {r[1]}..{r[2]} @@\n"+r[4]+"\n").encode())
class Memory:
    def __init__(self):
        self.state={"rebase":{}};self.meta=newmeta();self.history=[];self.last=[];self.twice={}
        self.usage=Counter()
    def trim(self,rr,cs,t,arm,budget,obj,ew,wm,off):
        size=sum(cs);idx=list(range(len(rr)))
        if size<=budget:return set()
        rank=order(rr,self.meta);priority={j:k for k,j in enumerate(rank)}
        if arm in ("lru","twice"):
            likes=lambda j:(self.twice.get((rr[j][0],(rr[j][1]-1)//12),0) if arm=="twice" else 0,-priority[j])
            evict=sorted(idx,key=likes)
            dropped=set()
            for j in evict:
                if size<=budget:break
                dropped.add(j);size-=cs[j]
            return dropped
        F,X,links=old.sx(rr,idx,self.meta,self.history,self.last,t,obj)
        z=sum(np.take(w,F[:,j]) for j,w in enumerate(ew));p=1/(1+np.exp(-np.clip(z+off,-25,25)))
        if arm=="global":width=np.tile(wm["global"],(len(rr),1))
        elif arm in ("typed","placebo"):
            b,ws=wm["typed"];scores=b+sum(np.asarray(w)[X[:,j]] for j,w in enumerate(ws))
            scores-=scores.max(axis=1,keepdims=True);width=np.exp(scores);width/=width.sum(axis=1,keepdims=True)
            if arm=="placebo" and len(idx)>1:width=np.roll(width,1+int(old.e.sha(obj["instance"]+str(t))[:8],16)%(len(idx)-1),axis=0)
        edges=[];by=[[] for j in idx];value=np.zeros(len(idx))
        for j in idx:
            chain=[j]
            for h in range(1 if arm=="point" else 3):
                if h:
                    row=rr[chain[-1]];nxt=links.get((row[0],row[2]+1))
                    if nxt is None:break
                    chain.append(nxt)
                w=float(p[j] if arm=="point" else p[j]*width[j,h]);eno=len(edges);edges.append((chain.copy(),w))
                for member in chain:by[member].append(eno);value[member]+=w
        active=[True]*len(edges);dropped=set();vers=[0]*len(rr)
        heap=[(value[j]/cs[j],-priority[j],j,0) for j in idx];heapq.heapify(heap)
        while size>budget:
            _,_,j,v=heapq.heappop(heap)
            if v!=vers[j] or j in dropped:continue
            dropped.add(j);size-=cs[j]
            for edge in by[j]:
                if not active[edge]:continue
                active[edge]=False;members,w=edges[edge]
                for m in members:
                    if m in dropped:continue
                    value[m]-=w;vers[m]+=1;heapq.heappush(heap,(max(0,value[m])/cs[m],-priority[m],m,vers[m]))
        return dropped
    def step(self,event,t,arm,budget,obj,ew,wm,off):
        name,args,fb=event;ss=self.state["rebase"]
        if name not in ("str_replace_editor","str_replace_based_edit_tool","edit_file") or not isinstance(args,dict):return
        write_event(self.history,event,ss,t);p=rel(args.get("path"));act=args.get("command")
        if success(act,p,fb):self.last[:]=[(p,len(str(args.get("old_str","")).splitlines()),t)]
        advance(self.state,self.meta,event,t);rr=pages(ss);cs=[cost(r) for r in rr]
        if arm=="twice":
            keys={(r[0],(r[1]-1)//12) for r in rr if r[3]==t}
            self.twice={k:min(2,self.twice.get(k,0)+int(k in keys)) for k in {(r[0],(r[1]-1)//12) for r in rr}}
        dead=self.trim(rr,cs,t,arm,budget,obj,ew,wm,off) if budget else set()
        for j in dead:
            q,a,b,_,_=rr[j];self.usage["evicted_pages"]+=1;self.usage["evicted_bytes"]+=cs[j]
            for ln in range(a,b+1):ss[q].pop(ln)
            if not ss[q]:del ss[q]
        retained=sum(cs)-sum(cs[j] for j in dead)
        if arm=="twice":
            keep={(r[0],(r[1]-1)//12) for j,r in enumerate(rr) if j not in dead}
            self.twice={k:v for k,v in self.twice.items() if k in keep}
        assert not budget or retained<=budget
        self.usage["events"]+=1;self.usage["retained_bytes_sum"]+=retained
        self.usage["retained_bytes_max"]=max(self.usage["retained_bytes_max"],retained)
def shard(k):
    ew=read(R2/"edit_memory/model.json")["flat"];wm=read(R2/"span_memory/width_model.json");off=read(R2/"span_memory/offset.json")["intercept"]
    with gzip.open(D/f"sealed_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=2) as out:
        for obj in rows(DATA/f"source_{k}.jsonl.gz"):
            policies={(a,b):Memory() for b in BUDGETS for a in ARMS};policies["unbounded",0]=Memory();catalog={};cuts=[];n=len(obj["events"])
            for t,event in enumerate(obj["events"],1):
                for (a,b),m in policies.items():m.step(event,t,a,b,obj,ew,wm,off)
                if t%4==0 and t<n:
                    views={}
                    for (a,b),m in policies.items():
                        ids=[]
                        for p,lo,hi,_,body in pages(m.state["rebase"]):
                            key=(p,lo,hi,body)
                            if key not in catalog:catalog[key]=len(catalog)
                            ids.append(catalog[key])
                        views[f"{a}@{b}"]=ids
                    cuts.append([t,views])
            rec=[obj["instance"],list(catalog),cuts,{f"{a}@{b}":dict(m.usage) for (a,b),m in policies.items()}]
            out.write(json.dumps(rec,separators=(",",":"))+"\n")
    return k
def main():
    files=[D/"PROTOCOL_RU.md",D/"replay.py",R2/"edit_memory/model.json",R2/"span_memory/width_model.json",R2/"span_memory/offset.json",R2/"edit_memory/experiment.py",R2/"span_memory/run.py",*sorted(DATA.glob("source_*.jsonl.gz"))]
    save(D/"method_lock.json",{str(p):old.e.sha(p.read_bytes()) for p in files})
    with ProcessPoolExecutor(4) as pool:
        for k in pool.map(shard,range(8)):print("sealed",k,flush=True)
    save(D/"decision_lock.json",{p.name:old.e.sha(p.read_bytes()) for p in [D/"method_lock.json",*sorted(D.glob("sealed_*.gz"))]})
if __name__=="__main__":main()
