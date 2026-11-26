"""Fit label-dependent models on training only, then seal metadata-only choices."""
import argparse
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

D = Path(__file__).resolve().parent
W = D.parents[1]
CAL = W / "graph_memory_round35/calibration_scale"
TRANSFER = W / "graph_memory_round35/calibration_transfer"
OFF = W / "graph_memory_round22/native_multiseed/official580"
FEAT = Path("D:/CodexResearch/x20-r33-budget-loss")
BUDGET = 2048
ARMS = ("strict","firstfit","rankdp","reachdp","greedy","alldp","nograph")
COLS = ("rank","tail_rank","dense_rank","cost","cost_share","role","structural_logit","prefix_count","output_fraction","free_fraction")
ABLATE = [i for i in range(len(COLS)) if COLS[i] not in ("role","structural_logit","output_fraction")]

def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def save(p,x):
    data=(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    data=gzip.compress(data,mtime=0) if p.suffix==".gz" else data
    if p.exists():
        assert p.read_bytes()==data,p
    else:
        tmp=p.with_suffix(p.suffix+".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

def linear(m,x):
    return x @ m["coef"] + m["intercept"]

def rankx(n):
    r=np.arange(1,n+1)
    return np.column_stack((-np.log(r),1/r,(n-r)/max(1,n-1)))

def tail(order,c,z,structural):
    cumulative=c[order].cumsum()
    k=int(cumulative.searchsorted(BUDGET,side="right"))
    slack=BUDGET-int(cumulative[k-1]) if k else BUDGET
    head=order[:k]
    ix=np.flatnonzero(c[order[k:]]<=slack)
    ids=order[k:][ix]
    f=np.column_stack((np.log1p(ix+k+1),np.log1p(ix+1),z[ids,0],z[ids,1],c[ids]/max(1,slack),
        z[ids,2],structural[ids],np.full(len(ids),np.log1p(k)),np.full(len(ids),z[head,2].mean() if k else 0.),
        np.full(len(ids),slack/BUDGET)))
    return head,slack,ix,ids,f

def fit():
    inv=read(CAL/"train-inventory.json")
    assert sha(CAL/"numeric-train.npz")==inv["npz"]
    folds=read(CAL/"fold-models.json")["folds"]
    model=read(CAL/"models.json")["models"]["oof_3894"]
    with np.load(CAL/"numeric-train.npz") as a:
        g,z,c,y=(a[k] for k in ("g","z","c","y"))
    assert np.min(c)>=0
    parts={"all":[],"reach":[]}
    start=0
    for q in inv["order"]:
        rec=inv["records"][q]; n=rec["n"]
        sl=slice(start,start+n); start+=n
        fold=folds[str(rec["fold"])]
        graph=linear(fold["graph_model"],g[sl])
        scores=graph+linear(fold["rank_model"],rankx(n))+(z[sl]-model["center"])/model["scale"]@model["weights"]
        order=np.argsort(-scores,kind="stable")
        head,slack,_,ids,x=tail(order,c[sl],z[sl],graph)
        if len(ids)==0:
            continue
        labels=y[sl].astype(bool)
        remains=order[len(head):][labels[order[len(head):]]]
        data=(x,labels[ids],np.full(len(ids),1./len(ids)))
        parts["all"].append(data)
        if len(remains) and c[sl][remains].sum()<=slack:
            parts["reach"].append(data)
    assert start==len(c) and len(inv["order"])==3894
    out={}
    for name,ds,cols in [("reachdp","reach",list(range(len(COLS)))),("nograph","reach",ABLATE),("alldp","all",list(range(len(COLS))))]:
        rows=parts[ds];x,y,w=(np.concatenate(a) for a in zip(*rows))
        x=x[:,cols]; scaler=StandardScaler().fit(x,sample_weight=w)
        est=LogisticRegression(C=1,max_iter=500).fit(scaler.transform(x),y,sample_weight=w)
        out[name]=dict(cols=cols,coef=est.coef_[0].tolist(),intercept=est.intercept_.item(),center=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),queries=len(rows),rows=len(y),positive=int(y.sum()),iterations=int(est.n_iter_[0]))
    save(D/"models.json",dict(models=out,features=COLS,train=sha(CAL/"numeric-train.npz"),folds=sha(CAL/"fold-models.json"),upstream=sha(CAL/"models.json"),
        code=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md"),cpp=sha(D/"choose.cpp")))
    print({k:(m["queries"],m["rows"],m["positive"]) for k,m in out.items()},flush=True)

def kernel():
    dll=Path(os.getenv("R39_KNAPSACK_DLL","D:/CodexResearch/x20-bench-workspace/tmp/r39-residual-choice.dll"))
    lib=ctypes.CDLL(str(dll))
    fn=lib.choose
    fn.argtypes=[ctypes.c_int,ctypes.c_int]+[np.ctypeslib.ndpointer(dtype=d,ndim=1,flags="C_CONTIGUOUS") for d in (np.int32,np.float64,np.uint8)]
    fn.restype=None
    def solve(c,g,s):
        v=np.zeros(len(c),dtype=np.uint8)
        fn(len(c),s,np.ascontiguousarray(c,dtype=np.int32),np.ascontiguousarray(g,dtype=np.float64),v)
        return np.flatnonzero(v)
    return solve

def fill(c,order,slack):
    take=[]
    for pos in order:
        if c[pos]<=slack:
            take.append(int(pos));slack-=int(c[pos])
    return sorted(take)

def selection(order,c,z,structural,models,solve):
    head,slack,ix,ids,x=tail(order,c,z,structural)
    choices={arm:[] for arm in ARMS}
    if len(ids):
        costs=c[ids]
        choices["firstfit"]=fill(costs,range(len(ids)),slack)
        choices["rankdp"]=solve(costs,np.log1p(1/(ix+1)),slack)
        for arm,m in models.items():
            logits=(x[:,m["cols"]]-m["center"])/m["scale"]@m["coef"] + m["intercept"]
            utility=np.logaddexp(0,logits)
            choices[arm]=solve(costs,utility,slack)
            if arm=="reachdp":
                density=np.divide(utility,costs,out=np.full(len(ids),np.inf),where=costs>0)
                choices["greedy"]=fill(costs,np.argsort(-density,kind="stable"),slack)
    extras={arm:ids[np.asarray(sel,dtype=int)].tolist() for arm,sel in choices.items()}
    assert all(c[v].sum()<=slack for v in extras.values())
    return dict(head=head.tolist(),slack=slack,eligible=len(ids),n=len(c),extra=extras)

def forecast(stage,seed):
    ms=read(D/"models.json");assert ms["code"]==sha(Path(__file__)) and ms["cpp"]==sha(D/"choose.cpp")
    sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
    import data as upstream
    rng=np.random.default_rng(8319);solve=kernel()
    for _ in range(80):
        c=rng.integers(0,12,8);g=rng.random(8);cap=int(rng.integers(0,30))
        mask=np.arange(256)[:,None]>>np.arange(8)&1
        opt=(mask@g)[mask@c<=cap].max()
        assert abs(g[solve(c,g,cap)].sum()-opt)<1e-10
    fp=FEAT/(stage+".json.gz")
    assert sha(fp)==read(W/"graph_memory_round33/budget_loss"/(stage+"-input.json"))["features"]
    raw={r["q"]:r for r in read(fp)}
    orders=read(CAL/(stage+"-orders.json.gz"))
    ranks={};natives={};links={}
    if stage=="test":
        for j in range(8):
            if seed!=13:
                p=TRANSFER/f"orders-{j}.json.gz";links[str(p.relative_to(W))]=sha(p)
                orders.update({q:v[str(seed)] for q,v in read(p).items()})
                p=W/f"graph_memory_round21/five_seed/seed-{seed}/picks-{j}.json.gz";links[str(p.relative_to(W))]=sha(p)
                ranks.update({r["q"]:r["dense"] for r in read(p)})
            for arm in ("full_rgcn","wo_chunk_adjacency"):
                p=OFF/f"seed-{seed}"/arm/f"picks-{j}.json.gz";links[str(p.relative_to(W))]=sha(p)
                for it in read(p):
                    natives.setdefault(it["q"],{})[arm]=it["graph"]
    else:
        assert seed==13
    pred={}
    for q,rawrow in raw.items():
        c=np.asarray(rawrow["c"],dtype=int);n=len(c)
        z=np.asarray(rawrow["x"]);graph=np.asarray(rawrow["o"])-linear(upstream.RANK,rankx(n))
        if seed!=13:
            z[ranks[q],0]=np.log1p(np.arange(1,n+1))
        rr={"R35":orders[q]["oof_3894"],**natives.get(q,{})};ps={}
        for key,idx in rr.items():
            assert sorted(idx)==list(range(n))
            ps[key]=selection(np.asarray(idx,dtype=int),c,z,graph,ms["models"],solve)
        pred[q]=[rawrow["t"],ps]
    pref=f"{stage}-{seed}"
    save(D/(pref+"-pred.json.gz"),pred)
    save(D/(pref+"-seal.json"),dict(prediction=sha(D/(pref+"-pred.json.gz")),model=sha(D/"models.json"),stage=stage,seed=seed,
        features=sha(fp),orders=sha(CAL/(stage+"-orders.json.gz")),links=links,rows=len(pred)))
    print("frozen",stage,seed,len(pred),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("stage",choices=["fit","dev","test"]);parser.add_argument("seeds",type=int,nargs="*");args=parser.parse_args()
    if args.stage=="fit":fit()
    else:
        for seed in args.seeds or [13]:forecast(args.stage,seed)

