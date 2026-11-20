"""Fit a conditional choice model for the first requested page, on the prior A panel only."""
import json,math,re
from collections import Counter
from pathlib import Path
import numpy as np
from shared import A,B,D,read,save,sha,stream,future,line_target,rows,prior

def features(pages,meta,last,issue):
    times=sorted({p[3] for p in pages},reverse=True);rec={t:i for i,t in enumerate(times)}
    filetimes=sorted({meta["paths"][p[0]] for p in pages},reverse=True);fc={t:i for i,t in enumerate(filetimes)}
    terms=prior.wordset(issue[:9000]);x=[]
    for path,lo,hi,age,body in pages:
        age_rank=rec[age];file_rank=fc[meta["paths"][path]]
        center=meta["center"][path];relative=((lo+hi)/2-center)/12;dist=abs(relative)
        tokens=prior.wordset(body)
        overlaps=tokens & terms; identifiers=sum("_" in w or len(w)>8 for w in overlaps)
        touched=last[0][0]==path if last else False
        tail=path.lower();base=tail.rsplit("/",1)[-1]
        x.append([age_rank==0,age_rank==1,age_rank==2,min(math.log1p(age_rank),3),
                  file_rank==0,file_rank==1,min(math.log1p(file_rank),3),min(math.log1p(dist),4),
                  min(math.log1p(dist),4)*(age_rank==0),relative>0,hi-lo==11,
                  min(3,len(overlaps)),min(3,identifiers),int(base.split(".")[0] in terms),
                  int("test" in tail),int("/" not in path),int(tail.endswith(".py")),int(touched),
                  min(math.log1p(meta["visits"][path]),3),int("def " in body),int("class " in body),
                  int(touched)*(age_rank==0)])
    return np.asarray(x,float)

def collect(src):
    examples=[];geometry=Counter()
    for file in sorted(src.glob("source_*.jsonl.gz")):
        for obj in rows(file):
            for t,pages,ids,meta,hist,last in stream(obj):
                edit=future(obj["events"],t)
                if not edit or not edit[2]:continue
                target=line_target(pages,edit[0],edit[1])
                if target is None:continue
                path,lo,hi,j=target
                X=features(pages,meta,last,obj["issue"])
                examples.append((X,j))
                if hi-lo+1<=48:geometry[((lo-1)%12,hi-lo+1)]+=1
    prior.wordset.cache_clear()
    return examples,geometry

def estimate(examples):
    xs=np.concatenate([v[0] for v in examples]);sizes=np.array([len(v[0]) for v in examples])
    offsets=np.cumsum(np.r_[0,sizes[:-1]]); ys=np.array([v[1] for v in examples])+offsets
    w=np.zeros(xs.shape[1]);reg=2
    def likelihood(beta):
        scores=xs @ beta;norm=np.maximum.reduceat(scores,offsets)
        p=np.exp(scores-np.repeat(norm,sizes));conc=np.add.reduceat(p,offsets)
        p/=np.repeat(conc,sizes)
        return float(-np.log(np.maximum(1e-60,p[ys])).sum()+reg*(beta@beta)/2),p
    for step in range(25):
        current,p=likelihood(w)
        xp=xs*p[:,None];mu=np.add.reduceat(xp,offsets,axis=0)
        grad=mu.sum(axis=0)-xs[ys].sum(axis=0)+reg*w
        H=xs.T@xp-mu.T@mu+reg*np.eye(xs.shape[1])
        delta=np.linalg.solve(H,grad)
        if np.max(np.abs(delta))<1e-7:break
        alpha=1
        while alpha>1e-6 and likelihood(w-alpha*delta)[0]>current:alpha*=.5
        w=w-alpha*delta
    return w

def calibration(examples,w):
    record=[]
    for xs,y in examples:
        z=xs@w;pr=np.exp(z-z.max());pr/=pr.sum()
        rec=xs[:,0].astype(float);rec=rec/rec.sum()
        j=np.argmax(pr);record.append([pr[y],pr[j],int(j==y),np.sum(pr**2)-2*pr[y]+1,len(xs),
                                       np.sum(rec**2)-2*rec[y]+1])
    a=np.asarray(record);bins=[]
    for low in np.arange(0,1,.1):
        use=(a[:,1]>=low)&(a[:,1]<(low+.10000001 if low>.89 else low+.1))
        if use.any():bins.append([int(use.sum()),float(a[use,1].mean()),float(a[use,2].mean())])
    return dict(n=len(a),first=float(a[:,2].mean()),nll=float(-np.log(a[:,0]).mean()),brier=float(a[:,3].mean()),
                brier_latest_cohort=float(a[:,5].mean()),ece=sum(n*abs(p-r) for n,p,r in bins)/len(a),bins=bins)

def main():
    train,geo=collect(A);val,_=collect(B);model=estimate(train)
    save(D/"risk_model.json",dict(beta=model.tolist(),geometry=[[off,n,count] for (off,n),count in sorted(geo.items())],
          training=len(train),excluded_from_geometry=len(train)-sum(geo.values()),source="real_swe (A) before R4",ridge=2))
    save(D/"risk_calibration_dev.json",dict(fit_A=calibration(train,model),development_B=calibration(val,model)))
    print(len(train),len(val),calibration(val,model)["first"])
if __name__=="__main__":main()
