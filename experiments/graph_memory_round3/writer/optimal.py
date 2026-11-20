"""Exact byte-budget resident selection for short connected intervals and a matched additive objective."""
import gzip,json,itertools
from concurrent.futures import ProcessPoolExecutor
import numpy as np
sysmod=__import__('sys')
import replay as rep
sysmod.path.insert(0,str(rep.D))
from replay import D,DATA,R2,Memory,old,rows,save,read,order,pages,cost
from score import locations,stats
DATA2=DATA/"replication";EXTRA=("additive_greedy","additive_exact","chain_exact")
def dynamic(cs,weights,limit):
    # Weights[:,h-1] are rewards ending at this page, for an h-page continuous interval.
    # A missing edge is represented by zero weight, even when a new path starts.
    n=len(cs);b=int(limit);path=np.zeros((n,2,b+1),dtype=np.int8)
    # states record consecutive kept *positions* in the sorted stream. Zero weight across a gap is enough.
    old=np.full((3,b+1),-np.inf);old[0]=0.
    for i,k in enumerate(cs):
        new=np.full_like(old,-np.inf);choices=np.argmax(old,axis=0)
        new[0]=np.max(old,axis=0);path[i,0]=choices
        if k<=b:
            sl=slice(None,b-k+1)
            one,two,three=weights[i]
            new[1,k:]=old[0,sl]+one
            base=old[1,sl]+one+two;extended=old[2,sl]+one+two+three
            new[2,k:]=np.maximum(base,extended);path[i,1,k:]=np.where(base>=extended,1,2)
        old=new
    s=int(np.argmax(old[:,b]));score=float(old[s,b]);kept=set()
    for i in range(n-1,-1,-1):
        if s==0:s=int(path[i,0,b])
        else:
            kept.add(i);s=0 if s==1 else int(path[i,1,b]);b-=cs[i]
    return kept,score
def gains(rr,obj,t,m,ew,wm,off):
    n=len(rr);idx=list(range(n))
    F,X,links=old.sx(rr,idx,m.meta,m.history,m.last,t,obj)
    p=1/(1+np.exp(-np.clip(off+sum(np.take(w,F[:,j]) for j,w in enumerate(ew)),-25,25)))
    b,ws=wm["typed"];zs=b+sum(np.asarray(w)[X[:,j]] for j,w in enumerate(ws));zs-=zs.max(axis=1,keepdims=True);w=np.exp(zs);w/=w.sum(axis=1,keepdims=True)
    v=np.zeros((n,3))
    for j,(f,a,b,_,s) in enumerate(rr):
        end=j
        for h in range(3):
            if h:
                end=links.get((f,rr[end][2]+1))
                if end is None:break
                assert end==j+h, "rows must be sorted by path and starting line"
            v[end,h]=p[j]*w[j,h]
    return v
def setvalue(kept,w):return sum(w[j,h] for j in kept for h in range(3) if h<=j and all(j-k in kept for k in range(1,h+1)))
def enumerate_check():
    rng=np.random.default_rng(55);checks=0
    for n in range(1,12):
        for _ in range(16):
            c=rng.integers(1,30,n).tolist();lim=int(rng.integers(1,max(2,sum(c)+1)));v=rng.random((n,3))
            for j in range(n):
                for h in range(1,3):
                    if h>j or rng.random()<.3:v[j,h]=0
            best,score=dynamic(c,v,lim)
            oracle=max((setvalue(set(s),v) for k in range(n+1) for s in itertools.combinations(range(n),k) if sum(c[j] for j in s)<=lim),default=0)
            assert sum(c[j] for j in best)<=lim and abs(score-oracle)<1e-9 and abs(setvalue(best,v)-oracle)<1e-9;checks+=1
    return checks
class Extended(Memory):
    def trim(self,rr,cs,t,arm,budget,obj,ew,wm,off):
        if arm not in EXTRA or sum(cs)<=budget:return super().trim(rr,cs,t,arm,budget,obj,ew,wm,off)
        v=gains(rr,obj,t,self,ew,wm,off);n=len(rr);ids=set(range(n))
        if "additive" in arm:
            add=v[:,0].copy()
            for h in (1,2):
                for shift in range(h+1):add[h-shift:n-shift]+=v[h:,h]/(h+1)
            v=np.stack((add,np.zeros(n),np.zeros(n)),axis=1)
        if arm=="additive_greedy":
            need=sum(cs);dead=set();rec=order(rr,self.meta);prio={j:k for k,j in enumerate(rec)}
            for j in sorted(ids,key=lambda j:(v[j,0]/cs[j],-prio[j],j)):
                if need<=budget:break
                need-=cs[j];dead.add(j)
            return dead
        kept,opt=dynamic(cs,v,budget)
        if arm=="chain_exact":
            gd=super().trim(rr,cs,t,"typed",budget,obj,ew,wm,off);before=setvalue(ids-gd,v);assert opt+1e-7>=before
            self.usage["local_decisions"]+=1;self.usage["local_better"]+=int(opt>before+1e-8)
        return ids-kept
def shard(k):
    ew=read(R2/"edit_memory/model.json")["flat"];wm=read(R2/"span_memory/width_model.json");off=read(R2/"span_memory/offset.json")["intercept"]
    with gzip.open(D/f"opt_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=2) as out:
        for obj in rows(DATA2/f"source_{k}.jsonl.gz"):
            states={(a,b):Extended() for a in (*rep.ARMS,*EXTRA) for b in rep.BUDGETS};states["unbounded",0]=Extended()
            cat={};cuts=[];n=len(obj["events"])
            for t,event in enumerate(obj["events"],1):
                for (a,b),st in states.items():st.step(event,t,a,b,obj,ew,wm,off)
                if t%4==0 and t<n:
                    views={}
                    for (a,b),m in states.items():
                        ids=[]
                        for p,lo,hi,_,body in pages(m.state["rebase"]):
                            key=(p,lo,hi,body)
                            if key not in cat:cat[key]=len(cat)
                            ids.append(cat[key])
                        views[f"{a}@{b}"]=ids
                    cuts.append([t,views])
            out.write(json.dumps([obj["instance"],list(cat),cuts,{f"{a}@{b}":dict(m.usage) for (a,b),m in states.items()}],separators=(",",":"))+"\n")
    return k
def evaluate():
    from pipeline import future
    from collections import Counter,defaultdict
    for n,h in read(D/"opt_lock.json").items():assert old.e.sha((D/n).read_bytes())==h
    gold=[];used=defaultdict(Counter);num=0;seen=set()
    for k in range(8):
        src={o["instance"]:o for o in rows(DATA2/f"source_{k}.jsonl.gz")}
        for i,cat,cuts,receipt in rows(D/f"opt_{k}.jsonl.gz"):
            seen.add(i)
            for a,u in receipt.items():
                mx=u.pop("retained_bytes_max",0);used[a].update(u);used[a]["max"]=max(used[a]["max"],mx)
            for t,views in cuts:
                num+=1;q=future(src[i]["events"],t)
                if not q or not q[2]:continue
                target=locations([cat[j] for j in views["unbounded@0"]],q[0],q[1]);m={}
                for a,v in views.items():
                    ls={n:s for j in v for f,lo,hi,body in [cat[j]] if f==q[0] for n,s in enumerate(body.split("\n"),lo)}
                    match=[ls.get(n)==s for n,s in target];m[a]=[int(bool(match) and all(match)),sum(match)/len(match) if match else 0,int(bool(match) and match[0])]
                gold.append([i,t,len(target),m])
    with gzip.open(D/"opt_scored.jsonl.gz","wt",encoding="utf8") as out:
        for row in gold:out.write(json.dumps(row,separators=(",",":"))+"\n")
    vec={a:np.array([r[3][a] for r in gold]) for a in gold[0][3]};grp=[r[0].split(".")[0] for r in gold];contrasts={}
    for b in rep.BUDGETS:
        for n,m in [("chain_exact","additive_exact"),("chain_exact","typed"),("typed","point"),("typed","global"),("typed","lru"),("typed","placebo"),("additive_exact","additive_greedy")]:
            l=f"{n}@{b}";r=f"{m}@{b}";contrasts[l+" minus "+r]={s:stats(vec[l][:,j],vec[r][:,j],grp) for j,s in enumerate(("whole","line_fraction","start"))}
    save(D/"optimal_results.json",dict(n=len(gold),projects=len(set(grp)),instances=len(seen),cuts=num,arms={a:dict(whole=int(v[:,0].sum()),fraction=float(v[:,1].mean()),start=int(v[:,2].sum()),usage=dict(used[a])) for a,v in vec.items()},paired=contrasts))
def main():
    checks=enumerate_check();oldsrc={o["instance"] for k in range(8) for o in rows(DATA/f"source_{k}.jsonl.gz")}
    newsrc={o["instance"] for k in range(8) for o in rows(DATA2/f"source_{k}.jsonl.gz")};assert not oldsrc&newsrc and not {i.split(".")[0] for i in oldsrc}&{i.split(".")[0] for i in newsrc}
    files=[D/"OPTIMAL_PROTOCOL.md",D/"optimal.py",D/"replay.py",D/"score.py",D/"method_lock.json",*sorted(DATA2.glob("source_*.gz"))]
    save(D/"opt_method_lock.json",dict(source={str(p):old.e.sha(p.read_bytes()) for p in files},bruteforce=checks,old_instances=len(oldsrc),new_instances=len(newsrc)))
    with ProcessPoolExecutor(4) as pool:
        for k in pool.map(shard,range(8)):print("sealed",k,flush=True)
    save(D/"opt_lock.json",{p.name:old.e.sha(p.read_bytes()) for p in [D/"opt_method_lock.json",*[D/f"opt_{k}.jsonl.gz" for k in range(8)]]})
    evaluate()
if __name__=="__main__":main()

