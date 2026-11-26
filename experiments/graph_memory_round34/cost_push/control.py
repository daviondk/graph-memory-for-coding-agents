"""Class-reversed TopPush risk with a certified convex optimization gap."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
R33=ROOT.parents[1]/"graph_memory_round33"
sys.path.insert(0,str(R33/"budget_loss"))
import losses as b
from study import paired
import numpy as np
from scipy.special import expit
from scipy.optimize import minimize
FAMILIES=("equal_quad","cost_quad","equal_log","cost_log")
def fit_risk(data,kind,l2):
    center=np.mean([x.mean(axis=0) for x,_,_,_ in data],axis=0)
    scale=np.sqrt(np.mean([((x-center)**2).mean(axis=0) for x,_,_,_ in data],axis=0));scale[scale<1e-9]=1
    xps=[];xns=[];ops=[];ons=[];ws=[]
    for x,o,c,y in data:
        x=(x-center)/scale;xps.append(x[y]);xns.append(x[~y]);ops.append(o[y]);ons.append(o[~y])
        wt=c[~y].astype(float) if kind.startswith("cost") else np.ones((~y).sum())
        if wt.sum()==0:wt[:]=1
        ws.append(wt/(wt.sum()*len(data)))
    npers=np.array(list(map(len,xps)));nners=np.array(list(map(len,xns)))
    qp=np.repeat(np.arange(len(data)),npers);qn=np.repeat(np.arange(len(data)),nners)
    sp0=np.r_[0,np.cumsum(npers)[:-1]];sn0=np.r_[0,np.cumsum(nners)[:-1]]
    xp=np.vstack(xps);xn=np.vstack(xns);op=np.concatenate(ops);on=np.concatenate(ons);wt=np.concatenate(ws)
    def obj(w,tau):
        pos=op+xp@w;neg=on+xn@w;minima=np.minimum.reduceat(pos,sp0)
        if tau:
            u=np.exp(-(pos-minima[qp])/tau);mass=np.add.reduceat(u,sp0)
            value=minima-tau*np.log(mass/npers);alpha=u/mass[qp]
        else:value=minima
        d=neg-value[qn]
        if kind.endswith("quad"):
            err=np.maximum(1.+d,0.);loss=err**2;g=wt*(2*err)
        else: loss=np.logaddexp(0.,d);g=wt*expit(d)
        objective=float(wt@loss+.5*l2*(w@w))
        if not tau:return objective
        group_grad=np.add.reduceat(g,sn0)
        return objective,l2*w+xn.T@g-xp.T@(alpha*group_grad[qp])
    w=np.zeros(4)
    eps=1e-5;check=np.array([(obj(w+v*eps,.25)[0]-obj(w-v*eps,.25)[0])/(2*eps) for v in np.eye(4)])
    assert np.allclose(check,obj(w,.25)[1],atol=5e-7)
    history=[]
    for t in [.25,.03,.003,.0003,.00003,.000002,.00000015,.00000001]:
        result=minimize(lambda z:obj(z,t),w,method="L-BFGS-B",jac=True,options={"ftol":1e-15,"gtol":1e-9,"maxiter":1000,"maxls":90})
        w=result.x;value,grad=obj(w,t)
        lower=value-grad@grad/(2*l2);upper=obj(w,0);gap=upper-lower
        history.append([t,float(lower),upper,float(gap),int(result.nit),bool(result.success)])
        if t<=.000002 and gap<=.0001:break
    assert -1e-12<=gap<=.0001,(kind,l2,gap)
    return {"weights":w.tolist(),"center":center.tolist(),"scale":scale.tolist(),"history":history}
def learn():
    src=b.PRIVATE/"train.json.gz";assert b.sha(src)==b.load(b.ROOT/"train-input.json")["features"]
    data=b.arrays(b.load(src));models={f"{k}_{l}":fit_risk(data,k,l) for k in FAMILIES for l in b.K}
    b.save(ROOT/"models.json",{"protocol":b.sha(ROOT/"PROTOCOL_RU.md"),"code":b.sha(Path(__file__)),"upstream":b.sha(src),"eligible":len(data),"models":models})
def predict(stage):
    path=b.PRIVATE/(stage+".json.gz");assert b.sha(path)==b.load(b.ROOT/(stage+"-input.json"))["features"]
    fit=b.load(ROOT/"models.json");allnames=fit["models"];sel=list(allnames) if stage=="dev" else b.load(ROOT/"select.json")["chosen"];out={}
    for r in b.load(path):
        x=np.array(r["x"]);o=np.array(r["o"]);arms={}
        for name in sel:
            m=allnames[name];arms[name]=np.argsort(-(o+(x-m["center"])/m["scale"]@m["weights"]),kind="stable").tolist()
        out[r["q"]]=arms
    p=ROOT/(stage+"-ranks.json.gz");b.save(p,out);b.save(ROOT/(stage+"-seal.json"),{"inputs":b.sha(path),"fit":b.sha(ROOT/"models.json"),"ranks":b.sha(p),"select":b.sha(ROOT/"select.json") if stage=="test" else None})
def evaluate(stage):
    p=ROOT/(stage+"-ranks.json.gz");assert b.sha(p)==b.load(ROOT/(stage+"-seal.json"))["ranks"]
    ranks=b.load(p);refs=b.load(b.R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else b.nm.OFF/"gold-spans.json.gz")
    old=b.load(b.ROOT/(stage+"-outcomes.json.gz"));out={}
    for path in b.sources(stage):
        for r in b.load(path):
            q=r["q"];base=[b.nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];gold=tuple(b.nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);arms={}
            for name,order in ranks[q].items():
                assert sorted(order)==list(range(len(base)));ns=tuple(base[i] for i in order)
                vals=[b.nm.pilot.span_metrics_under_token_budget(ns,gold,k) for k in (512,1024,2048)]
                arms[name]=[vals[-1].full_support,*[v.coverage for v in vals],b.nm.span_metrics_at(ns,gold,5).coverage,b.nm.span_mrr(ns,gold)]
            arms["R33"]=old[q]["arms"]["cost_worst_0.03"];out[q]={"t":r["t"],"arms":arms}
    b.save(ROOT/(stage+"-outcomes.json.gz"),out)
    names=list(next(iter(out.values()))["arms"]);means={k:np.mean([r["arms"][k] for r in out.values()],axis=0).tolist() for k in names}
    if stage=="dev":
        chosen=[]
        for a in FAMILIES:
            arm=[f"{a}_{l}" for l in sorted(b.K,reverse=True)];chosen.append(max(arm,key=lambda n:(round(means[n][0],12),round(means[n][3],12),-arm.index(n))))
        b.save(ROOT/"select.json",{"chosen":chosen,"means":means,"outcomes":b.sha(ROOT/"dev-outcomes.json.gz")});return
    contrasts={}
    for other in b.load(ROOT/"select.json")["chosen"]:
        by={q:{"t":r["t"],"arms":{"global":r["arms"][other],"candidate":r["arms"]["R33"]}} for q,r in out.items()}
        contrasts[other]=paired(by,"candidate")
    b.save(ROOT/"results.json",{"n":len(out),"means":means,"contrasts":contrasts,"seal":b.sha(ROOT/"test-seal.json")})
if __name__=="__main__":
    learn()
    for split in ("dev","test"):
        predict(split);evaluate(split);print(split,flush=True)
