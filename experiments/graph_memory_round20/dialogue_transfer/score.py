"""Compute paired macro metrics from persisted text-free predictions only."""
import collections
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
for v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[v] = "1"
import numpy as np
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parent
ARMS=("original","edge","shifted")
BUDGETS=(.1,.2,.4)

def load(n):
    b=(ROOT/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)

def write(name, obj):
    p=ROOT/name
    raw=(json.dumps(obj,indent=None if name.endswith("gz") else 2,allow_nan=False,separators=(",",":") if name.endswith("gz") else None)+"\n").encode()
    if name.endswith("gz"):
        raw=gzip.compress(raw,compresslevel=5,mtime=0)
    if p.exists():
        assert raw==p.read_bytes(),name
    else:
        p.write_bytes(raw)

def groups(rows, gold):
    out={}
    for r in rows:
        k=r["id"]
        y=np.array(gold[k],dtype=int)
        rec={"n":len(y),"p":int(y.sum()),"arms":{}}
        for arm,s in r["scores"].items():
            s=np.array(s)
            assert len(y)==len(s) and np.all((s>=0)&(s<=1))
            order=np.argsort(-s)
            auc=float(roc_auc_score(y,s)) if 0<sum(y)<len(y) else None
            m={"auc":auc}
            ties={}
            for b in BUDGETS:
                t=math.ceil(b*len(s))
                key="R"+str(round(100*b))
                m[key]=float(y[order[:t]].sum()/y.sum()) if y.sum() else None
                ties[key]=bool(t<len(s) and s[order[t-1]]==s[order[t]])
            rec["arms"][arm]=dict(metric=m,ties=ties)
        out[k]=rec
    return out

def summary(g, keys, components):
    out={"groups":len(keys),"usable":sum(g[k]["p"]>0 for k in keys),"mean":{},"contrasts":{}}
    for a in ARMS:
        mean={}
        for m in ("R20","auc","R10","R40"):
            v=[g[k]["arms"][a]["metric"][m] for k in keys if g[k]["arms"][a]["metric"][m] is not None]
            mean[m]=float(np.mean(v)) if v else None
        out["mean"][a]=mean
    for b in ("original","shifted"):
        out["contrasts"][b]={}
        for m in out["mean"]["edge"]:
            ks=[k for k in keys if g[k]["arms"]["edge"]["metric"][m] is not None]
            diff={k:g[k]["arms"]["edge"]["metric"][m]-g[k]["arms"][b]["metric"][m] for k in ks}
            per=collections.defaultdict(list)
            for k in ks:
                per[components[k]].append(diff[k])
            arr=np.array(list(diff.values()))
            nc=len(per)
            res=dict(n=len(arr),clusters=nc,delta=float(np.mean(arr)) if len(arr) else None,
                     wins=int(sum(arr>1e-13)),losses=int(sum(arr< -1e-13)),ties=int(sum(abs(arr)<=1e-13)),ci=None)
            if nc>1:
                sums=np.array([sum(a) for a in per.values()])
                ns=np.array([len(a) for a in per.values()])
                rng=np.random.default_rng(13)
                batch=rng.integers(0,nc,size=(10000,nc))
                vals=sums[batch].sum(axis=1)/ns[batch].sum(axis=1)
                res["ci"]=np.quantile(vals,[.025,.975]).tolist()
            out["contrasts"][b][m]=res
    return out

def main():
    split=load("split.json.gz")
    ext=load("external-forecast.json.gz")
    dmn=load("domain-forecast.json.gz")
    for name in ("external","domain"):
        assert hashlib.sha256((ROOT/f"{name}-forecast.json.gz").read_bytes()).hexdigest()==load(f"{name}-forecast-lock.json")["predictions"]
    a=groups(ext,load("external-gold.json.gz"))
    b=groups(dmn,load("domain-gold.json.gz"))
    dg=load("domain-groups.json")
    sums=dict(external=summary(a,list(a),split["components"]),
              disjoint=summary(a,split["selected"],{k:k for k in split["selected"]}),
              within=summary(b,list(b),dg))
    write("group-metrics.json.gz",{"external":a,"within":b})
    write("results.json",sums)
    for k,s in sums.items():
        print(k,s["groups"],s["usable"],s["mean"],s["contrasts"]["original"]["R20"],flush=True)
if __name__=="__main__":
    main()
