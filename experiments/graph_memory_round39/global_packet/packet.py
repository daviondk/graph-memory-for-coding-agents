"""Train probability models on observed train labels and freeze budget-constrained evidence sets."""
import argparse
import importlib.util
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("residual_choice",D.parent/"remaining_budget"/"reader.py")
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
from sklearn.ensemble import HistGradientBoostingClassifier
np=base.np
read,save,sha=base.read,base.save,base.sha
W,CAL=base.W,base.CAL
B=2048
THRESHOLDS=(0,512,1024,1536,2048)
DENSE=(0,1,7)
FOUND=read(CAL/"models.json")["models"]["oof_3894"]

def feature(z,graph,offset):
    s=graph+offset+(z-FOUND["center"])/FOUND["scale"]@FOUND["weights"]
    order=np.argsort(-s,kind="stable");rank=np.empty(len(z),dtype=int);rank[order]=np.arange(1,1+len(z))
    x=np.column_stack((z[:,0],z[:,1],z[:,2],graph,s,s.max()-s,np.log1p(rank),np.full(len(z),np.log1p(len(z)))))
    return x,order

def portable(trees,x):
    score=np.full(len(x),trees["base"],dtype=float)
    for tree in trees["trees"]:
        def visit(i,ids):
            f,threshold,left,right,value=tree[i]
            if left==right:
                score[ids]+=value
            else:
                split=x[ids,f]<=threshold
                if split.any():visit(left,ids[split])
                if not split.all():visit(right,ids[~split])
        visit(0,np.arange(len(x)))
    return score

def fit():
    inventory=read(CAL/"train-inventory.json")
    assert inventory["npz"]==sha(CAL/"numeric-train.npz")
    folds=read(CAL/"fold-models.json")["folds"];parts=[]
    with np.load(CAL/"numeric-train.npz") as arr:
        g,z,y=(arr[k] for k in ("g","z","y"))
    cursor=0;weights=[]
    for q in inventory["order"]:
        v=inventory["records"][q];n=v["n"];sl=slice(cursor,cursor+n);cursor+=n
        fold=folds[str(v["fold"])];gx=base.linear(fold["graph_model"],g[sl]);ox=base.linear(fold["rank_model"],base.rankx(n))
        x,_=feature(z[sl],gx,ox);parts.append(x);weights.append(np.full(n,1/n))
    x=np.vstack(parts);sw=np.concatenate(weights);sw=sw/sw.mean()
    assert len(x)==len(y)==cursor and len(parts)==3894
    models={}
    for name,cols in [("graph",list(range(x.shape[1]))),("dense",list(DENSE))]:
        data=x[:,cols]
        m=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,l2_regularization=2,learning_rate=.08,
             early_stopping=False,random_state=3910).fit(data,y,sample_weight=sw)
        trees=[]
        for p in m._predictors:
            nodes=p[0].nodes
            trees.append([[int(a["feature_idx"]),float(a["num_threshold"]),int(a["left"]),int(a["right"]),float(a["value"])] for a in nodes])
        models[name]=dict(base=float(m._baseline_prediction.item()),cols=cols,trees=trees)
        take=np.linspace(0,len(data)-1,8001).astype(int)
        assert np.allclose(portable(models[name],data[take]),m.decision_function(data[take]),rtol=0,atol=1e-10)
    save(D/"models.json",dict(models=models,rows=cursor,queries=len(parts),positive=int(y.sum()),train=inventory["npz"],
        code=sha(D/"packet.py"),protocol=sha(D/"PROTOCOL_RU.md"),shared=sha(D.parent/"remaining_budget/reader.py")))

def projections(stage,seed):
    fp=base.FEAT/(stage+".json.gz")
    assert sha(fp)==read(W/"graph_memory_round33/budget_loss"/(stage+"-input.json"))["features"]
    raw=read(fp)
    r13=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"];rs=r13
    ranks={};expected=read(CAL/(stage+"-orders.json.gz"))
    if seed!=13:
        root=W/f"graph_memory_round21/five_seed/seed-{seed}"
        rs=read(root/"calibration.json")["rank"]
        for i in range(8):
            ranks.update({r["q"]:r["dense"] for r in read(root/f"picks-{i}.json.gz")})
            expected.update({q:z[str(seed)] for q,z in read(base.TRANSFER/f"orders-{i}.json.gz").items()})
    registry={};all_x=[];start=0
    for r in raw:
        q=r["q"];z=np.asarray(r["x"]);n=len(z);rx=base.rankx(n)
        old=base.linear(r13,rx);g=np.asarray(r["o"])-old
        dense=np.asarray(ranks[q] if ranks else list(range(n)))
        z[dense,0]=np.log1p(np.arange(1,n+1));rr=np.empty(n);rr[dense]=base.linear(rs,rx)
        x,order=feature(z,g,rr);assert order.tolist()==expected[q]["oof_3894"]
        registry[q]=(r["t"],np.array(r["c"],dtype=int),order,dense,slice(start,start+n));start+=n;all_x.append(x)
    return registry,np.vstack(all_x)

def select(order,c,u,threshold,method,solve):
    cumulative=c[order].cumsum();k=int(cumulative.searchsorted(threshold,side="right"))
    head=order[:k];cap=B-int(c[head].sum())
    ids=order[k:][c[order[k:]]<=cap]
    if method=="firstfit":
        ids=ids[base.fill(c[ids],range(len(ids)),cap)]
    elif method=="greedy":
        ids=ids[base.fill(c[ids],np.argsort(-u[ids]/c[ids],kind="stable"),cap)]
    else:
        values=u[ids] if method=="dp" else np.log1p(1/(np.argsort(order)[ids]-k+1))
        ids=ids[solve(c[ids],values,cap)]
    result=np.concatenate([head,ids]).tolist()
    assert len(set(result))==len(result) and c[result].sum()<=B
    return result

def forecast(stage,seed):
    m=read(D/"models.json");assert m["code"]==sha(D/"packet.py")
    registry,x=projections(stage,seed);solve=base.kernel()
    utility={name:np.logaddexp(0,portable(v,x[:,v["cols"]])) for name,v in m["models"].items()};out={}
    chosen=None if stage=="dev" else read(D/"dev-selection.json")
    for q,(t,c,graph,dense,sl) in registry.items():
        arms={}
        for key,order in (("graph",graph),("dense",dense)):
            u=utility[key][sl]
            thresholds=THRESHOLDS if chosen is None else [chosen["thresholds"][key]]
            for T in thresholds:
                for method in (["dp"] if chosen is None else ["dp","greedy","rankdp"]):
                    name=f"{key}-{T}-{method}" if chosen is None else key+"-"+method
                    arms[name]=select(order,c,u,T,method,solve)
        arms["R35-firstfit"]=select(graph,c,utility["graph"][sl],B,"firstfit",solve)
        out[q]=[t,arms]
    key=f"{stage}-{seed}";save(D/(key+"-pred.json.gz"),out)
    save(D/(key+"-seal.json"),dict(packet=sha(D/(key+"-pred.json.gz")),model=sha(D/"models.json"),features=sha(base.FEAT/(stage+".json.gz")),
        dev_selection=sha(D/"dev-selection.json") if chosen else None,rows=len(out)))
    print("frozen",key,len(out),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage");p.add_argument("seeds",type=int,nargs="*");a=p.parse_args()
    if a.stage=="fit":fit()
    else:
        for seed in a.seeds or [13]:forecast(a.stage,seed)

