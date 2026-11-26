"""Fit train-only offset logistic models. Score functions accept observable arrays only."""
from input_rows import D,PRIVATE,R20,OFF,R19,load,sha,write,np,f,M
from scipy.optimize import minimize
from scipy.special import expit
K=(.03,.3)
ALPHAS=(0,.25,.5,.75,1,1.25,1.5,2,3)
FAMILIES=("global","uncert","text","both")
def signal(n,m):
    return f.lin(m,f.rank_x(n))
def standard(v,avg,scale):
    return np.clip((v-avg)/np.maximum(scale,1e-8),-4.,4.)
def covars(n,p,x,fam):
    l=np.log(np.arange(1,n+1))
    columns=[p,l,np.maximum(0,l-np.log(3)),np.maximum(0,l-np.log(10)),
             np.maximum(0,p+1),np.maximum(0,p),np.maximum(0,p-1),p*l]
    if fam in ("uncert","both"):columns.extend(p*a for a in x[:4])
    if fam in ("text","both"):columns.extend(p*a for a in x[4:])
    return np.column_stack(columns)
def train():
    recs=load(PRIVATE/"train.json.gz");d=load(D/"train-inputs.json");assert d["features"]==sha(PRIVATE/"train.json.gz")
    cal=load(M)["rank"];source=load(OFF/"split.json.gz")
    tids={v["t"] for v in recs}
    assert tids <= {v["t"] for v in source["train"]} and not tids.intersection({v["t"] for v in source["dev"]+source["test"]})
    active=[r for r in recs if 0<len(r["y"])<len(r["p"])]
    c=np.asarray([r["x"] for r in active]);ca=c.mean(axis=0);cs=c.std(axis=0)
    res={};y=[];w=[];offset=[]
    for r in active:
        n=len(r["p"]);a=np.zeros(n);a[r["y"]]=1.;y.extend(a)
        w.extend(np.where(a>0,.5/a.sum(),.5/(n-a.sum()))/len(active));offset.extend(signal(n,cal)+np.array(r["p"]))
    y,w,offset=(np.asarray(v) for v in (y,w,offset))
    for fam in FAMILIES:
        X=np.vstack([covars(len(r["p"]),np.asarray(r["p"]),standard(np.asarray(r["x"]),ca,cs),fam) for r in active])
        avg=np.average(X,axis=0,weights=w);scale=np.sqrt(np.average((X-avg)**2,axis=0,weights=w))
        X=standard(X,avg,scale);X=np.column_stack([np.ones(len(X)),X])
        for k in K:
            def objective(b):
                s=offset+X@b
                obj=np.sum(w*(np.logaddexp(0.,s)-y*s))+.5*k*(b[1:]@b[1:])
                grad=X.T@(w*(expit(s)-y));grad[1:]+=k*b[1:];return obj,grad
            result=minimize(objective,np.zeros(X.shape[1]),jac=True,method="L-BFGS-B",options={"ftol":1e-12,"gtol":1e-7,"maxiter":500})
            assert result.success,str(result.message)
            name=f"{fam}_{k}";res[name]={"family":fam,"penalty":k,"coef":result.x.tolist(),"avg":avg.tolist(),"scale":scale.tolist(),"objective":float(result.fun),"iterations":result.nit}
    write(D/"models.json",{"rank":cal,"context_avg":ca.tolist(),"context_scale":cs.tolist(),"models":res,"eligible":len(active),"n":len(recs),"rows":len(y),"train":sha(D/"train-inputs.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"models.py")})
def names():
    return ["dense","factor"]+[f"alpha_{v}" for v in ALPHAS]+[f"{m}_{k}" for m in FAMILIES for k in K]
def order(r,model,name):
    p=np.asarray(r["p"]);n=len(p);base=signal(n,model["rank"])
    if name=="dense":return np.arange(n)
    if name=="factor":s=base+p
    elif name.startswith("alpha_"):s=base+float(name.split("_")[1])*p
    else:
        m=model["models"][name];xs=standard(np.asarray(r["x"]),np.asarray(model["context_avg"]),np.asarray(model["context_scale"]))
        z=covars(n,p,xs,m["family"]);z=standard(z,np.array(m["avg"]),np.array(m["scale"]));coef=np.array(m["coef"]);s=base+p+coef[0]+z@coef[1:]
    return np.argsort(-s,kind="stable")
def forecast(split):
    model=load(D/"models.json");assert model["code"]==sha(D/"models.py")
    if split=="dev":arms=names()
    else:
        lock=load(D/"dev-selection.json");assert lock["models"]==sha(D/"models.json")
        arms=list(dict.fromkeys(["dense","factor",*lock["selected"].values()]))
    rows=load(PRIVATE/(split+".json.gz"));meta=load(D/(split+"-inputs.json"));assert meta["file"]==sha(PRIVATE/(split+".json.gz"))
    out=[{"q":r["q"],"t":r["t"],"rank":{arm:order(r,model,arm).tolist() for arm in arms}} for r in rows]
    dst=D/(split+"-ranks.json.gz");write(dst,out)
    write(D/(split+"-seal.json"),{"arms":arms,"models":sha(D/"models.json"),"input":sha(D/(split+"-inputs.json")),"rank":sha(dst),"selection":None if split=="dev" else sha(D/"dev-selection.json")})
if __name__=="__main__":
    import sys
    if sys.argv[1]=="train":train()
    else:forecast(sys.argv[1])