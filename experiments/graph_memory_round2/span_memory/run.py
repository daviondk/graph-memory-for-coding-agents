"""Learn the next span width on training repositories; optimize exact set coverage for three reads."""
import gzip, hashlib, itertools, json, math, sys
from functools import lru_cache
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
D=Path(__file__).resolve().parent;E=D.parent/"edit_memory"
sys.path.insert(0,str(E))
import experiment as e
from common import newmeta,pages,advance,success,rel,rows
from policy import CAP,order,gen_features,unique_span
from pipeline import future
def save(name,x): (D/name).write_text(json.dumps(x,indent=1),encoding="utf8")
def read(name):return json.loads((D/name).read_bytes())
def evidence(seq,step,current,i,links):
    path,a,b,age,body=seq[i];previous=current[0] if current else ("",0,-100)
    flat=[int(path==previous[0]),min(5,previous[1]),min(6,step-previous[2])]
    lines=body.splitlines();nonempty=[s for s in lines if s.strip()]
    indent=lambda s:min(6,(len(s)-len(s.lstrip()))//2)
    def declaration(s):return int(s.lstrip().startswith(("class ","def ","async def ")))
    raw=[min(5,len(lines)//3),int(a%12==1 and b-a==11),min(5,len(body)//100),
         indent(nonempty[0]) if nonempty else 0,indent(nonempty[-1]) if nonempty else 0,
         min(3,sum(declaration(s) for s in lines))]
    for j in range(2):
        target=links.get((path,b+1))
        if target is None:
            raw.extend([2,2,7,2]);continue
        q,na,nb,t1,code=seq[target]
        nxt=next((s for s in code.splitlines() if s.strip()),"")
        raw.extend([int(t1==age),int(nb-na==11),indent(nxt),declaration(nxt)])
        b=nb;age=t1
    return flat+raw
DIMS=[2,6,7,6,2,6,7,7,4]+[3,3,8,3]*2
def stream(obj):
    states={"rebase":{}};meta=newmeta();hist=[];last=[];ev=obj["events"];iid=obj["instance"]
    for t,event in enumerate(ev,1):
        name,args,feedback=event
        e.write_event(hist,event,states["rebase"],t)
        if isinstance(args,dict) and success(args.get("command"),rel(args.get("path")),feedback):
            last[:]=[(rel(args.get("path")),len(str(args.get("old_str","")).splitlines()),t)]
        advance(states,meta,event,t)
        if t%4==0 and t<len(ev):
            rr=pages(states["rebase"]);idx=order(rr,meta)[:CAP]
            yield t,rr,idx,meta,hist,last
def sx(seq,idx,meta,hist,last,t,obj):
    paths=sorted({r[0] for r in seq});links={(r[0],r[1]):i for i,r in enumerate(seq)}
    f=[gen_features(seq[i],meta,t,obj["issue"])+e.extra(seq[i],hist,t,paths,obj["instance"])[:8] for i in idx]
    x=[evidence(seq,t,last,i,links) for i in idx]
    return np.asarray(f,dtype=int),np.asarray(x,dtype=int),links
def train_shard(k):
    split=e.read("split.json");sh=split["shards"][k];ids=set(sh["ids"]);ex=set(split["test"]);samples=[]
    for obj in rows(Path(sh["file"])):
        iid=obj["instance"]
        if iid not in ids or iid.split(".")[0] in ex:continue
        ids.remove(iid)
        for t,rr,idx,meta,hist,last in stream(obj):
            q=future(obj["events"],t)
            if not q or not q[2]:continue
            span=unique_span(rr,q[0],q[1])
            if not span or span[0] not in idx:continue
            links={(r[0],r[1]):i for i,r in enumerate(rr)}
            samples.append([evidence(rr,t,last,span[0],links),min(4,len(span))-1])
    return samples
def train():
    with ProcessPoolExecutor(4) as pool: samples=[a for s in pool.map(train_shard,range(len(e.all_files()))) for a in s]
    X=np.array([s[0] for s in samples]);Y=np.eye(4)[[s[1] for s in samples]]
    freq=(Y.sum(axis=0)+1)/(len(Y)+4);model={"global":freq.tolist(),"n":len(Y),"widths":Y.sum(axis=0).astype(int).tolist()}
    for arm,ncol in [("history",3),("typed",len(DIMS))]:
        dims=DIMS[:ncol];offset=np.cumsum([0,*dims[:-1]])
        keys=X[:,:ncol]+offset;W=np.zeros((sum(dims),4));b=np.log(freq)
        for _ in range(180):
            z=b+W[keys].sum(axis=1);z-=z.max(axis=1,keepdims=True);P=np.exp(z);P/=P.sum(axis=1,keepdims=True)
            err=(P-Y)/len(Y);grad=np.stack([np.bincount(keys.ravel(),weights=np.repeat(err[:,j],ncol),minlength=len(W)) for j in range(4)],axis=1)
            W-=.5*(grad+.001*W);b-=.5*err.sum(axis=0)
        model[arm]=[b.tolist(),[W[l:l+d].tolist() for l,d in zip(offset,dims)]]
    save("width_model.json",model)
@lru_cache(maxsize=49)
def triples(n):
    return np.array(list(itertools.combinations(range(n),3)),dtype=np.int16).T
def exact(seq,idx,links,weights):
    n=len(idx)
    if n<=3:return list(idx)
    # Count singleton, pair, and (only if all three pages connect) triple mass exactly once.
    inv={v:j for j,v in enumerate(idx)};S=weights[:,0];P=np.zeros((n,n));nxt=np.full(n,-1,dtype=int)
    for j,i in enumerate(idx):
        path,a,b,_,_=seq[i];q=links.get((path,b+1))
        if q not in inv:continue
        k=inv[q];P[j,k]=P[k,j]=weights[j,1];nxt[j]=k
    # Sparse list of complete chains keyed by candidate positions in sorted order.
    a,b,c=triples(n);v=S[a]+S[b]+S[c]+P[a,b]+P[b,c]+P[a,c]
    for j in range(n):
        k=nxt[j]
        if k<0 or nxt[k]<0:continue
        lo,mi,hi=sorted((j,k,nxt[k]))
        # Lexicographic rank of (lo,mi,hi) in combinations(range(n),3).
        rank=math.comb(n,3)-math.comb(n-lo,3)+math.comb(n-lo-1,2)-math.comb(n-mi,2)+hi-mi-1
        v[rank]+=weights[j,2]
    z=int(np.argmax(v));return [idx[q] for q in (a[z],b[z],c[z])]
def evaluate_shard(args):
    mode,k=args; wm=read("width_model.json"); ew=e.read("model.json")["flat"];sh=D/f"fresh_{k}.jsonl.gz"
    with gzip.open(D/f"{mode}_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=2) as out:
        for obj in rows(sh):
            for t,rr,idx,meta,hist,last in stream(obj):
                if mode=="gold":
                    q=future(obj["events"],t)
                    if q and q[2]:
                        span=unique_span(rr,q[0],q[1]) or [];e.packed(out,[obj["instance"],t,list(span),int(bool(span) and len(span)<=3 and set(span)<=set(idx))])
                    continue
                choices={a:idx[:3] for a in ["recent","pointwise","global","history","typed","placebo"]}
                if len(idx)>3:
                    F,X,links=sx(rr,idx,meta,hist,last,t,obj)
                    raw=sum(np.take(w,F[:,c]) for c,w in enumerate(ew))
                    # Recover absolute logit intercept from training feature totals in a separate fit-independent file.
                    p=1/(1+np.exp(-np.clip(raw+read("offset.json")["intercept"],-25,25)))
                    choices["pointwise"]=[idx[j] for j in np.argsort(-p,kind="stable")[:3]]
                    W={}
                    W["global"]=np.tile(wm["global"],(len(idx),1))
                    for name in ["history","typed","placebo"]:
                        key="typed" if name=="placebo" else name
                        b,ws=wm[key];m=X.copy()
                        if name=="placebo":
                            shift=1+int(e.sha(obj["instance"]+str(t))[:8],16)%(len(idx)-1)
                            m[:,3:]=np.roll(m[:,3:],shift,axis=0)
                        z=b+sum(np.asarray(w)[m[:,c]] for c,w in enumerate(ws));z-=z.max(axis=1,keepdims=True);Z=np.exp(z);W[name]=Z/Z.sum(axis=1,keepdims=True)
                    for a,w in W.items():choices[a]=exact(rr,idx,links,w*p[:,None])
                e.packed(out,[obj["instance"],t,choices,{a:sum(len(rr[j][4]) for j in sel) for a,sel in choices.items()}])
def offset():
    # Retrieve the intercept of E's exact logistic fit from the same training rows and optimizer.
    pairs=[r for f in sorted(E.glob("train_*.gz")) for r in rows(f)];cols=e.ARMS["flat"]
    X=np.array([r[0] for r in pairs],dtype=np.int16)[:,cols];y=np.array([r[1] for r in pairs]);w=np.where(y,1.,4.);w/=w.sum()
    dims=np.array(e.DIMS+e.EXTRA)[cols];ofs=np.cumsum([0,*dims[:-1]]);keys=X+ofs;coef=np.zeros(sum(dims));inter=np.log((w*y).sum()/(w*(1-y)).sum())
    for _ in range(120):
        z=np.clip(inter+coef[keys].sum(axis=1),-25,25);err=(1/(1+np.exp(-z))-y)*w
        grad=np.bincount(keys.ravel(),weights=np.repeat(err,len(cols)),minlength=len(coef))
        coef-=4*(grad+.0005*coef);inter-=4*sum(err)
    assert np.max(np.abs(coef-np.concatenate(e.read("model.json")["flat"])))<1e-8
    save("offset.json",{"intercept":float(inter)})
def main():
    files=[D/"PROTOCOL.md",D/"acquire.py",D/"run.py",E/"model.json",E/"split.json",D/"selection.json",*sorted(D.glob("fresh_*.gz"))]
    save("method_lock.json",{str(f):e.sha(f.read_bytes()) for f in files});offset();train()
    for mode in ["pred","gold"]:
        with ProcessPoolExecutor(4) as pool:list(pool.map(evaluate_shard,[(mode,k) for k in range(8)]))
        if mode=="pred":save("decision_lock.json",{f.name:e.sha(f.read_bytes()) for f in [D/"method_lock.json",D/"width_model.json",D/"offset.json",*sorted(D.glob("pred_*.gz"))]})
if __name__=="__main__":main()

