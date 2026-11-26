"""Fit fixed-dimensional ranking corrections on equal-weighted training questions."""
from data import *
FAM=("point","pairs","worst","cost_worst")
K=(.03,.3)
def arrays(rows):
    return [(np.array(r["x"]),np.array(r["o"]),np.array(r["c"]),np.isin(np.arange(len(r["c"])),r["y"])) for r in rows if 0<len(r["y"])<len(r["c"])]

def solve(data,kind,l2):
    center=np.mean([x.mean(axis=0) for x,_,_,_ in data],axis=0)
    scale=np.sqrt(np.mean([((x-center)**2).mean(axis=0) for x,_,_,_ in data],axis=0));scale[scale<1e-9]=1
    cooked=[((x-center)/scale,off,cost,y) for x,off,cost,y in data];has_intercept=kind=="point"
    def objective(b):
        total=0.;grad=np.zeros_like(b);w=b[:4]
        for x,off,c,y in cooked:
            s=off+x@w
            if kind=="point":
                s=s+b[4];weight=np.where(y,.5/y.sum(),.5/(len(y)-y.sum()))
                total+=weight@(np.logaddexp(0.,s)-y*s)
                error=weight*(expit(s)-y);grad[:4]+=x.T@error;grad[4]+=error.sum();continue
            xp,xn=x[y],x[~y];sp,sn=s[y],s[~y]
            if kind=="pairs":
                diff=sn[:,None]-sp;total+=np.logaddexp(0.,diff).mean()
                ds=expit(diff)/diff.size;grad+=xn.T@ds.sum(axis=1)-xp.T@ds.sum(axis=0)
            else:
                a=-sp/.25;lse=logsumexp(a);softmin=-.25*(lse-np.log(len(sp)));weighted_x=xp.T@np.exp(a-lse)
                weights=c[~y].astype(float) if kind=="cost_worst" else np.ones(len(sn))
                if not weights.sum():weights=np.ones(len(sn))
                weights/=weights.sum();d=sn-softmin
                total+=weights@np.logaddexp(0.,d);ds=weights*expit(d);grad+=xn.T@ds-ds.sum()*weighted_x
        grad/=len(data);grad[:4]+=l2*w
        return total/len(data)+.5*l2*(w@w),grad
    zero=np.zeros(5 if has_intercept else 4)
    value,delta=objective(zero);eps=1e-5
    measured=np.array([(objective(zero+v*eps)[0]-objective(zero-v*eps)[0])/(2*eps) for v in np.eye(len(zero))])
    assert np.allclose(delta,measured,atol=1e-6)
    res=minimize(objective,zero,jac=True,method="L-BFGS-B",options={"ftol":1e-12,"gtol":1e-7,"maxiter":300})
    assert res.success
    return {"weights":res.x[:4].tolist(),"intercept":float(res.x[4]) if has_intercept else 0.,"center":center.tolist(),"scale":scale.tolist(),"objective":float(res.fun),"iterations":res.nit}
def fit():
    path=PRIVATE/"train.json.gz";assert load(ROOT/"train-input.json")["features"]==sha(path);rows=arrays(load(path))
    mods={f"{kind}_{l2}":solve(rows,kind,l2) for kind in FAM for l2 in K}
    save(ROOT/"models.json",{"models":mods,"eligible":len(rows),"code":sha(Path(__file__)),"protocol":sha(ROOT/"PROTOCOL_RU.md"),"rows":sha(path)})
def forecast(split):
    path=PRIVATE/(split+".json.gz");assert sha(path)==load(ROOT/(split+"-input.json"))["features"]
    models=load(ROOT/"models.json")["models"];learned=list(models) if split=="dev" else list(dict.fromkeys(load(ROOT/"selection.json")["chosen"].values()))
    rows={}
    for rec in load(path):
        x=np.array(rec["x"]);o=np.array(rec["o"]);arms={"frozen":np.argsort(-o,kind="stable").tolist()}
        for name in learned:
            m=models[name];s=o+((x-m["center"])/m["scale"])@m["weights"];arms[name]=np.argsort(-s,kind="stable").tolist()
        rows[rec["q"]]=arms
    fn=ROOT/(split+"-ranks.json.gz");save(fn,rows)
    save(ROOT/(split+"-seal.json"),{"rank":sha(fn),"models":sha(ROOT/"models.json"),"source":sha(path),"selection":sha(ROOT/"selection.json") if split=="test" else None})
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:forecast(sys.argv[1])
