"""Regularized interval bottleneck fit with exact enumeration of the two latent assignments."""
from geometry import *
from itertools import product
from scipy.special import expit
from scipy.optimize import minimize
def optimized(fun,x):
    return minimize(fun,x,method="L-BFGS-B",jac=True,options={"ftol":1e-15,"gtol":1e-9,"maxls":90,"maxiter":900})
def standardize(rows):
    cols=[np.asarray(r["x"]) for r in rows]
    center=np.mean([x.mean(0) for x in cols],0)
    scale=np.sqrt(np.mean([((x-center)**2).mean(0) for x in cols],0));scale[scale<1e-9]=1.
    records=[]
    for r,x in zip(rows,cols):
        y=np.asarray(r["y"]);neg=np.setdiff1d(np.arange(len(x)),y);c=np.asarray(r["c"])[neg].astype(float)
        assert len(y) and len(neg) and c.sum()>0
        records.append(((x-center)/scale,np.asarray(r["o"]),y,neg,c/c.sum()/len(rows)))
    return center,scale,records
def fit_pair(records,reg):
    deltas=[];bias=[];weights=[]
    for x,o,y,n,w in records:
        deltas.append((x[n,None,:]-x[y][None,:,:]).reshape(-1,4));bias.append((o[n,None]-o[y][None,:]).ravel())
        weights.append(np.repeat(w/len(y),len(y)))
    arr=np.vstack(deltas);off=np.concatenate(bias);wt=np.concatenate(weights)
    def fun(v):
        d=off+arr@v;return wt@np.logaddexp(0.,d)+reg*w2(v),arr.T@(wt*expit(d))+reg*v
    v=optimized(fun,np.zeros(4)).x;obj,grad=fun(v);assert np.linalg.norm(grad)<1e-6
    return v,float(obj)
def w2(v):return .5*(v@v)
def fit_fixed(records,selected,reg):
    xp=[];xn=[];op=[];on=[];wg=[]
    for (x,o,yp,n,w),h in zip(records,selected):
        ids=np.asarray(sorted(set(h)));xp.append(x[ids]);op.append(o[ids]);xn.append(x[n]);on.append(o[n]);wg.append(w)
    pn=np.array(list(map(len,xp)));nn=np.array(list(map(len,xn)));qp=np.repeat(np.arange(len(records)),pn);qn=np.repeat(np.arange(len(records)),nn)
    p0=np.r_[0,np.cumsum(pn)[:-1]];n0=np.r_[0,np.cumsum(nn)[:-1]]
    xp=np.vstack(xp);xn=np.vstack(xn);op=np.concatenate(op);on=np.concatenate(on);wg=np.concatenate(wg)
    def fun(v,t):
        pos=op+xp@v;neg=on+xn@v;low=np.minimum.reduceat(pos,p0)
        if t:
            mass=np.exp(-(pos-low[qp])/t);z=np.add.reduceat(mass,p0);threshold=low-t*np.log(z/pn);a=mass/z[qp]
        else:threshold=low
        d=neg-threshold[qn];obj=wg@np.logaddexp(0.,d)+reg*w2(v)
        if not t:return float(obj)
        h=wg*expit(d);return obj,xn.T@h-xp.T@(a*np.add.reduceat(h,n0)[qp])+reg*v
    v=np.zeros(4);history=[]
    for t in (.25,.03,.003,.0003,.00003,2e-6,1.5e-7):
        v=optimized(lambda z:fun(z,t),v).x;obj,grad=fun(v,t);lower=float(obj-(grad@grad)/(2*reg));upper=fun(v,0)
        history.append([t,lower,upper]);assert lower<=upper+1e-12
        if t<=2e-6 and upper-lower<=1e-6:break
    assert upper-lower<=1e-5
    return v,lower,upper,history
def learn():
    atoms=load(D/"train-atoms.json.gz");rows=feature("train")
    eligible=[r for r in rows if 0<len(r["y"])<len(r["c"])]
    center,scale,rec=standardize(eligible)
    groups=[buckets(atoms[r["q"]]) for r in eligible]
    options=[(k,g) for k,gs in enumerate(groups) for g in gs if len(g)>1];assert len(options)==1
    qidx,alts=options[0];assert len(alts)==2
    def fixed(k):
        return [[(g[0] if len(g)==1 else k) for g in gs] for gs in groups]
    def preferred(v):
        x,o,*_=rec[qidx];s=o+x@v;return max(alts,key=lambda i:(s[i],-i))
    def true_obj(v,reg):
        total=reg*w2(v)
        for (x,o,y,n,w),gs in zip(rec,groups):
            s=o+x@v;threshold=min(max(s[i] for i in g) for g in gs)
            total+=w@np.logaddexp(0.,s[n]-threshold)
        return float(total)
    out={};cert={}
    for source,family in ((B,"cost_worst"),(C,"cost_log")):
        for k,m in load(source/"models.json")["models"].items():
            if k.startswith(family+"_"):
                assert np.allclose(center,m["center"]) and np.allclose(scale,m["scale"]);out[k]=m
    def fmt(v):return dict(weights=v.tolist(),center=center.tolist(),scale=scale.tolist())
    for reg in (.03,.3):
        pair,pobj=fit_pair(rec,reg);out[f"per_positive_{reg}"]={**fmt(pair),"loss":pobj}
        branches={}
        for alt in alts:
            v,lo,hi,history=fit_fixed(rec,fixed(alt),reg)
            branches[alt]=dict(weights=v.tolist(),lower=lo,upper=hi,true_risk=true_obj(v,reg),preferred=preferred(v),history=history)
        best=min(alts,key=lambda k:(branches[k]["true_risk"],k));baseline=preferred(np.zeros(4));global_lo=min(b["lower"] for b in branches.values());global_hi=branches[best]["true_risk"]
        assert -1e-12<global_hi-global_lo<1e-5
        for fam,k in (("witness",best),("fixed",baseline)):out[f"{fam}_{reg}"]=fmt(np.array(branches[k]["weights"]))
        starts={"zero":np.zeros(4),"hard":np.asarray(out[f"cost_log_{reg}"]["weights"]),"per_positive":pair}
        paths={}
        for name,v in starts.items():
            path=[];node=preferred(v)
            for j in range(12):
                path.append(node);nxt=branches[node]["preferred"]
                if node==nxt:break
                node=nxt
            paths[name]=path
        cert[str(reg)]=dict(branches=branches,global_lower=global_lo,global_upper=global_hi,gap=global_hi-global_lo,chosen=best,frozen_witness=baseline,multistart_paths=paths)
    p=D/"models.json";save(p,dict(models=out,cert=cert,original_queries=len(rows),eligible=len(eligible),choice_query=eligible[qidx]["q"],alternative_indices=alts,
        training=sha(D/"train-atoms.json.gz"),feature_rows=sha(old.PRIVATE/"train.json.gz"),base_hashes={str(t):sha(t/"models.json") for t in (B,C)},plan=sha(D/"PROTOCOL_RU.md"),addendum=sha(D/"TRAIN_ADDENDUM_RU.md"),code=sha(Path(__file__))))
    print("fit",len(eligible),{k:(v["chosen"],v["frozen_witness"],v["gap"]) for k,v in cert.items()},flush=True)
def forecast(stage):
    m=load(D/"models.json")["models"];names=list(m) if stage=="dev" else list(dict.fromkeys(load(D/"selection.json")["chosen"].values()))
    out={}
    for r in feature(stage):
        x=np.asarray(r["x"]);o=np.asarray(r["o"]);out[r["q"]]={n:ranks(o+(x-m[n]["center"])/m[n]["scale"]@m[n]["weights"]).tolist() for n in names}
    p=D/(stage+"-ranks.json.gz");save(p,out)
    save(D/(stage+"-rank-seal.json"),dict(models=sha(D/"models.json"),ranks=sha(p),features=sha(old.PRIVATE/(stage+".json.gz")),selection=sha(D/"selection.json") if stage=="test" else None))
if __name__=="__main__":
    if sys.argv[1]=="fit":learn()
    else:forecast(sys.argv[1])