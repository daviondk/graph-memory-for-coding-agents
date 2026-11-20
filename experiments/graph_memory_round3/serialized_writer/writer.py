"""Every call receives only bytes, one editor event, an immutable issue and fixed model weights."""
import gzip,hashlib,heapq,json,math,os,sys,time,zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
R2=HERE.parents[1]/"graph_memory_round2";DATA=HERE.parent/"context"/"replication";sys.path.insert(0,str(R2/"span_memory"))
import run as F
from experiment import write_event
from common import newmeta,pages,advance,rel,success,rows
from policy import order,wordset
BUDGETS=(4096,12288);ARMS=("lru","point","typed")
def h(x):return hashlib.sha256(x).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(n,x):(HERE/n).write_text(json.dumps(x,ensure_ascii=True,indent=1),encoding="utf8")
def line(f,x):f.write(json.dumps(x,separators=(",",":"),ensure_ascii=True)+"\n")
def empty(arm):return pack([arm,0,[],[],[]])
def jsonbytes(x):return json.dumps(x,sort_keys=False,ensure_ascii=False,separators=(",",":")).encode("utf8")
def pack(x):return b"SW3"+zlib.compress(jsonbytes(x),3)
def payload(blob):
    assert blob[:3]==b"SW3";return json.loads(zlib.decompress(blob[3:]))
def materialize(x):
    arm,t,files,hist,last=x;ss={};meta=newmeta()
    for path,info,runs in files:
        access,center=info[:2];meta["paths"][path]=access;meta["center"][path]=center/2
        if arm!="lru":
            meta["visits"][path]=info[2]
            if info[3]>=0:meta["edited"][path]=info[3]
        mem={}
        for lo,when,lines_ in runs:
            for j,s in enumerate(lines_,lo):mem[j]=(s,when)
        ss[path]=mem
    history=[[p,n,step,set(words),set()] for p,n,step,words in hist]
    return t,{"rebase":ss},meta,history,[tuple(q) for q in last]
def snapshot(arm,t,ss,meta,hist,last,rr,omitted):
    files={}
    # Resident addresses only. Coordinates and ages are losslessly grouped into maximal runs.
    for j,page in enumerate(rr):
        if j in omitted:continue
        p,lo,hi,age,code=page
        runs=files.setdefault(p,[])
        for n in range(lo,hi+1):
            s,when=ss[p][n]
            if runs and when==runs[-1][1] and runs[-1][0]+len(runs[-1][2])==n:runs[-1][2].append(s)
            else:runs.append([n,when,[s]])
    fs=[]
    for p,runs in sorted(files.items()):
        info=[meta["paths"].get(p,0),int(round(2*meta["center"].get(p,0)))]
        if arm!="lru":info.extend((meta["visits"].get(p,0),meta["edited"].get(p,-1)))
        fs.append([p,info,runs])
    hs=[[p,n,step,sorted(add|sub,key=lambda x:(-len(x),x))[:64]] for p,n,step,add,sub in hist] if arm!="lru" else []
    return [arm,t,fs,hs,last if arm=="typed" else []]
def eviction_order(arm,rr,meta,hist,last,t,obj,w):
    ids=list(range(len(rr)));rank=order(rr,meta);priority={j:m for m,j in enumerate(rank)}
    if arm=="lru":return list(reversed(rank))
    ew,wm,off=w;fs,x,edges=F.sx(rr,ids,meta,hist,last,t,obj)
    z=sum(np.take(a,fs[:,j]) for j,a in enumerate(ew));p=1/(1+np.exp(-np.clip(z+off,-25,25)))
    cs=np.array([len((f"@@ {r[0]} {r[1]}..{r[2]} @@\n"+r[4]+"\n").encode()) for r in rr])
    n=len(rr)
    if arm=="point":return sorted(ids,key=lambda j:(p[j]/cs[j],-priority[j],j))
    intercept,ws=wm["typed"];s=intercept+sum(np.asarray(v)[x[:,j]] for j,v in enumerate(ws));s-=s.max(axis=1,keepdims=True)
    width=np.exp(s);width/=width.sum(axis=1,keepdims=True)
    by=[[] for _ in rr];chains=[];values=np.zeros(n);versions=[0]*n
    for j,r in enumerate(rr):
        selected=[j]
        for k in range(3):
            if k:
                q=rr[selected[-1]];nxt=edges.get((q[0],q[2]+1))
                if nxt is None:break
                selected.append(nxt)
            v=float(p[j]*width[j,k]);ix=len(chains);chains.append((selected.copy(),v))
            for m in selected:by[m].append(ix);values[m]+=v
    active=[True]*len(chains);heap=[(values[j]/cs[j],-priority[j],j,0) for j in ids];heapq.heapify(heap);dead=set();out=[]
    while len(out)<n:
        _,_,j,version=heapq.heappop(heap)
        if version!=versions[j] or j in dead:continue
        dead.add(j);out.append(j)
        for ix in by[j]:
            if not active[ix]:continue
            active[ix]=False;members,impact=chains[ix]
            for m in members:
                if m in dead:continue
                values[m]=max(0,values[m]-impact);versions[m]+=1
                heapq.heappush(heap,(values[m]/cs[m],-priority[m],m,versions[m]))
    return out
def transition(blob,event,static,weights,budget):
    old=payload(blob);arm=old[0];t,state,meta,hist,last=materialize(old);t+=1
    if arm!="lru":write_event(hist,event,state["rebase"],t)
    name,args,output=event
    if arm=="typed" and isinstance(args,dict):
        path=rel(args.get("path"));cmd=args.get("command")
        if success(cmd,path,output):last[:]=[(path,len(str(args.get("old_str","")).splitlines()),t)]
    advance(state,meta,event,t)
    ss=state["rebase"];rr=pages(ss)
    obj={"instance":static["instance"],"issue":static["issue"]}
    # Capture even when the event is opaque: the logical clock is part of the state.
    def encode(removed):
        return pack(snapshot(arm,t,ss,meta,hist,last,rr,removed))
    full=encode(set());before=len(full);calls=1;evicted=0
    if before<=budget:out=full
    else:
        evictions=eviction_order(arm,rr,meta,hist,last,t,obj,weights) if rr else []
        def trial(k):return encode(set(evictions[:k]))
        n=len(rr);lo=0;hi=min(1,n)
        out=trial(hi);calls+=1
        while len(out)>budget and hi<n:
            lo=hi;hi=min(n,2*hi);out=trial(hi);calls+=1
        if len(out)<=budget:
            while lo+1<hi:
                mid=(lo+hi)//2;proposal=trial(mid);calls+=1
                if len(proposal)<=budget:hi=mid;out=proposal
                else:lo=mid
            evicted=hi
        else:
            evicted=n;out=pack([arm,t,[],[],[]]);calls+=1
    assert len(out)<=budget
    # Old wordset uses an LRU for pure feature extraction. Leave no text keys resident between events.
    wordset.cache_clear()
    return out,(before,len(out),evicted,calls)
def run(k):
    wm=read(R2/"span_memory/width_model.json");ew=read(R2/"edit_memory/model.json")["flat"];off=read(R2/"span_memory/offset.json")["intercept"]
    weights=ew,wm,off;times=Counter();start=time.monotonic();N=0
    with gzip.open(HERE/f"cuts_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=4) as out,gzip.open(HERE/f"events_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=4) as log:
        for task in rows(DATA/f"source_{k}.jsonl.gz"):
            iid=task["instance"];const={"instance":iid,"issue":task["issue"]};blobs={(a,b):empty(a) for b in BUDGETS for a in ARMS}
            for t,event in enumerate(task["events"],1):
                N+=1;packets=[];obs=[]
                for (a,b),blob in blobs.items():
                    tick=time.perf_counter_ns()
                    new,metrics=transition(blob,event,const,weights,b)
                    times[a]+=time.perf_counter_ns()-tick
                    blobs[a,b]=new;before,sz,drops,npack=metrics
                    obs.append([a,b,h(new),sz,before,drops,npack])
                    if t%4==0 and t<len(task["events"]):
                        # External logger only, never passed to transition; JSON preserves exact canonical compressed bytes.
                        x=payload(new)
                        assert pack(x)==new and x[1]==t
                        packets.append([a,b,h(new),x])
                line(log,[iid,t,obs])
                if packets:line(out,[iid,t,packets])
    return dict(k=k,events=N,wall=time.monotonic()-start,transition_ns=dict(times))
def main():
    paths=[HERE/"PROTOCOL_RU.md",HERE/"writer.py",R2/"span_memory/run.py",R2/"edit_memory/experiment.py",R2/"edit_memory/model.json",R2/"span_memory/width_model.json",R2/"span_memory/offset.json",*sorted(DATA.glob("source_*.gz"))]
    save("method_lock.json",{str(p):h(p.read_bytes()) for p in paths})
    os.environ["OPENBLAS_NUM_THREADS"]="1"
    with ProcessPoolExecutor(4) as pool:out=list(pool.map(run,range(8)))
    save("timing.json",out)
    save("checkpoint_lock.json",{p.name:h(p.read_bytes()) for p in [HERE/"method_lock.json",*sorted(HERE.glob("cuts_*.gz")),*sorted(HERE.glob("events_*.gz"))]})
    print(out,flush=True)
if __name__=="__main__":main()
