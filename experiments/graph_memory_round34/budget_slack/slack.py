"""Source-only weighted four-parameter calibration; no gold at inference."""
import os
for key in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[key]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import sys,hashlib,json,gzip
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1];B=W/"graph_memory_round33/budget_loss"
sys.path.insert(0,str(B));import data as old
from data import f,nm,np,load,sha,RANK,R19,R20,REL
from scipy.optimize import minimize
from scipy.special import expit,logsumexp
K=(.3,.03);TRANS=("soft","sqrt");SEEDS=(13,17,29,37,41);BUD=2048
def save(p,o):
    b=json.dumps(o,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(gzip.compress(b,mtime=0,compresslevel=3) if p.suffix==".gz" else b);tmp.replace(p)
def source(s):
    p=old.PRIVATE/(s+".json.gz");assert load(B/(s+"-input.json"))["features"]==sha(p);return load(p)
def weights(P,N,group,form):
    mask=(P<=BUD)&((P+N)>BUD)
    if group in ("r33","equal"):return np.ones(len(P)) if group=="r33" else mask.astype(float)
    r=N/(BUD-P+1 if group=="slack" else BUD) if group=="length" else np.divide(N,np.maximum(1,BUD-P+1))
    val=np.sqrt(r) if form=="sqrt" else r/(1+r)
    return val*mask
def fit():
    row=source("train");data=[r for r in row if 0<len(r["y"])<len(r["c"])]
    x=[np.array(r["x"]) for r in data];mean=np.mean([a.mean(axis=0) for a in x],axis=0);sd=np.sqrt(np.mean([((a-mean)**2).mean(axis=0) for a in x],axis=0));sd[sd<1e-9]=1
    P=[];N=[];cooked=[]
    for r,xx in zip(data,x):
        xx=(xx-mean)/sd;y=np.zeros(len(xx),bool);y[r["y"]]=True;c=np.array(r["c"]);off=np.asarray(r["o"])
        P.append(c[y].sum());N.append(c[~y].sum());v=c[~y].astype(float);assert v.sum()>0
        cooked.append((xx[y],xx[~y],off[y],off[~y],v/v.sum()))
    P=np.array(P);N=np.array(N)
    m={};facts={};perq={r["q"]:dict(t=r["t"],P=int(p),N=int(n),L=BUD-int(p)+1,w={}) for r,p,n in zip(data,P,N)}
    for group in ("r33","equal","length","slack"):
        for form in (["flat"] if group in ("r33","equal") else TRANS):
            raw=weights(P,N,group,form);ws=raw/raw.sum();fam=group+"_"+form
            facts[fam]={"n_active":int((ws>0).sum()),"ess":float(1/(ws@ws)),"max_share":float(ws.max())}
            for q,v in zip(perq,ws):perq[q]["w"][fam]=float(v)
            for l2 in ((.03,) if group=="r33" else K):
                def loss(w):
                    tot=0.;g=np.zeros(4)
                    for s,(xp,xn,op,on,cost) in zip(ws,cooked):
                        if s==0:continue
                        a=-(op+xp@w)/.25;lse=logsumexp(a);low=-.25*(lse-np.log(len(a)));dx=xp.T@np.exp(a-lse);d=on+xn@w-low
                        tot+=s*(cost@np.logaddexp(0.,d));ds=cost*expit(d);g+=s*(xn.T@ds-ds.sum()*dx)
                    return tot+.5*l2*(w@w),g+l2*w
                zero=np.zeros(4);_,grad=loss(zero);diff=np.array([(loss(v*1e-5)[0]-loss(-v*1e-5)[0])/(2e-5) for v in np.eye(4)])
                assert np.max(np.abs(diff-grad))<1e-6
                opt=minimize(loss,zero,jac=True,method="L-BFGS-B",options={"gtol":1e-7,"ftol":1e-12,"maxiter":300});assert opt.success
                name=f"{fam}_{l2}";m[name]={"weights":opt.x.tolist(),"objective":opt.fun,"group":group,"form":form,"l2":l2}
                if group=="r33":
                    known=load(B/"models.json")["models"]["cost_worst_0.03"];assert np.max(np.abs(opt.x-known["weights"]))<1e-6
                    # Use the exact archived coefficients for the preexisting benchmark comparator.
                    m[name]["refit_max_error"]=float(np.max(np.abs(opt.x-known["weights"])));m[name]["weights"]=known["weights"]
    save(D/"train-query-weights.json.gz",perq);save(D/"models.json",dict(models=m,mean=mean.tolist(),sd=sd.tolist(),weights=facts,rows=sha(D/"train-query-weights.json.gz"),protocol=sha(D/"PROTOCOL_RU.md"),code=sha(D/"slack.py")))
def rank(x,base,model,names,mm,indices):
    z=(x-np.array(model["mean"]))/model["sd"]
    return {a:indices[np.argsort(-(base+z@mm[a]["weights"]),kind="stable")].tolist() for a in names}
def predict(stage):
    models=load(D/"models.json");mm=models["models"]
    names=list(mm);selected=None
    if stage=="test":
        sel=load(D/"selection.json");selected=sha(D/"selection.json");assert sel["models"]==sha(D/"models.json")
        names=list(dict.fromkeys(sel["chosen"].values()))
    rows=source(stage)
    if stage=="dev":
        ranks={r["q"]:rank(np.array(r["x"]),np.array(r["o"]),models,names,mm,np.arange(len(r["o"]))) for r in rows}
        p=D/"dev-ranks.json.gz";save(p,ranks);save(D/"dev-seal.json",{"ranks":sha(p),"models":sha(D/"models.json")});return
    by={r["q"]:r for r in rows};R21=W/"graph_memory_round21/five_seed";files={}
    for i in range(8):
        originals=load(old.sources(stage)[i]);out={}
        for seed in SEEDS:
            if seed!=13:
                sd=R21/f"seed-{seed}";p=sd/f"picks-{i}.json.gz";cert=load(sd/"forecast-seal.json")
                assert sha(p)==next(c["sha"] for c in cert["receipts"] if c["file"]==p.name) and sha(sd/"calibration.json")==cert["rank_weights"]
                pos={r["q"]:r["dense"] for r in load(p)};cal=load(sd/"calibration.json")["rank"]
            for rr in originals:
                q=rr["q"];r=by[q];n=len(r["o"]);dx=np.arange(n) if seed==13 else np.array(pos[q]);x=np.array(r["x"])[dx];x[:,0]=np.log1p(np.arange(1,n+1))
                bas=np.array(r["o"]) if seed==13 else (np.array(r["o"])-f.lin(RANK,f.rank_x(n)))[dx]+f.lin(cal,f.rank_x(n))
                out.setdefault(q,{})[str(seed)]=rank(x,bas,models,names,mm,dx)
        pp=D/f"test-ranks-{i}.json.gz";save(pp,out);files[pp.name]=sha(pp)
        print("sealed",i,len(out),flush=True)
    save(D/"test-seal.json",{"files":files,"chosen":selected,"models":sha(D/"models.json"),"code":sha(D/"slack.py"),"protocol":sha(D/"PROTOCOL_RU.md")})
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:predict(sys.argv[1])