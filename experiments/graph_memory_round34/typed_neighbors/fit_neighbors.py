"""Add equally regularized cost-weighted worst-positive corrections to the frozen base."""
from channels import D,CACHE,load,sha,save,np
from scipy.optimize import minimize
from scipy.special import logsumexp,expit
import sys
COLUMNS={"self":[0],"raw":[0,*range(1,9)],"additive":[0,*range(9,17)],
         "agreement":[0,*range(9,18)],"rewired":[0,*range(18,27)]}
ARMS=["frozen","self","raw","additive","rewired","agreement","transplant"]
def fit():
    path=CACHE/"train.json.gz";assert load(D/"train-inputs.json")["rows_file"]==sha(path)
    raw=load(path);rows=[r for r in raw if 0<len(r["y"])<len(r["o"])];models={}
    for arm,cols in COLUMNS.items():
        design=[np.array(r["x"])[:,cols] for r in rows];mean=np.mean([x.mean(axis=0) for x in design],axis=0)
        sd=np.sqrt(np.mean([((x-mean)**2).mean(axis=0) for x in design],axis=0));sd[sd<1e-9]=1.
        data=[]
        for r,x in zip(rows,design):
            x=(x-mean)/sd;off=np.array(r["o"]);cost=np.array(r["c"]);y=np.zeros(len(x),bool);y[r["y"]]=True
            cost=cost[~y].astype(float)
            if cost.sum()==0:cost=np.ones(len(cost))
            data.append((x[y],x[~y],off[y],off[~y],cost/cost.sum()))
        def objective(w):
            total=0.;grad=np.zeros_like(w)
            for p,n,po,no,weight in data:
                a=-(po+p@w)/.25;lse=logsumexp(a);softmin=-.25*(lse-np.log(len(a)));xp=p.T@np.exp(a-lse)
                diff=no+n@w-softmin;ds=weight*expit(diff);total+=weight@np.logaddexp(0.,diff);grad+=n.T@ds-ds.sum()*xp
            return total/len(data)+.015*(w@w),grad/len(data)+.03*w
        zero=np.zeros(len(cols));fd=np.array([(objective(zero+v*1e-5)[0]-objective(zero-v*1e-5)[0])/2e-5 for v in np.eye(len(zero))])
        assert np.max(np.abs(fd-objective(zero)[1]))<1e-6
        out=minimize(objective,zero,jac=True,method="L-BFGS-B",options={"ftol":1e-12,"gtol":1e-7,"maxiter":300})
        assert out.success
        models[arm]=dict(columns=cols,mean=mean.tolist(),sd=sd.tolist(),w=out.x.tolist(),objective=out.fun,iterations=out.nit)
    save(D/"models.json",{"models":models,"n":len(rows),"train":sha(path),"code":sha(D/"fit_neighbors.py"),"protocol":sha(D/"PROTOCOL_RU.md")})
def predict(stage):
    p=CACHE/(stage+".json.gz");assert load(D/(stage+"-inputs.json"))["rows_file"]==sha(p)
    if stage=="test":assert load(D/"selection.json")["identified"]
    weights=load(D/"models.json")["models"];out={}
    for r in load(p):
        x=np.asarray(r["x"]);base=np.array(r["o"]);ranks={}
        for arm in ARMS:
            if arm=="frozen":s=base
            else:
                m=weights["agreement" if arm=="transplant" else arm];cols=COLUMNS["rewired"] if arm=="transplant" else m["columns"]
                s=base+((x[:,cols]-m["mean"])/m["sd"])@m["w"]
            ranks[arm]=np.argsort(-s,kind="stable").tolist()
        out[r["q"]]={"t":r["t"],"ranks":ranks}
    path=D/(stage+"-ranks.json.gz");save(path,out)
    save(D/(stage+"-seal.json"),{"ranks":sha(path),"model":sha(D/"models.json"),"input":sha(p),"chosen":sha(D/"selection.json") if stage=="test" else None})
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:predict(sys.argv[1])