"""Native metrics on fitted forecasts and analytic controls. Paired group bootstrap."""
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score
HERE=Path(__file__).resolve().parent
ARMS=("original","role_pct","calibrated","edge","shifted","uniform","user_first")
BUDGET=(.1,.2,.4)
PAIRS=(("calibrated","original"),("edge","shifted"),("edge","calibrated"),("calibrated","user_first"),("role_pct","user_first"))

def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.name.endswith(".gz") else data)

def save(p,x):
    b=json.dumps(x,separators=(",",":"),allow_nan=False).encode()+b"\n"
    if p.name.endswith(".gz"):
        b=gzip.compress(b,compresslevel=5,mtime=0)
    if p.exists():
        assert p.read_bytes()==b
    else:
        p.write_bytes(b)

def group(y,u,scores):
    n=len(y)
    g=int(sum(map(int,y)))
    counts={"n":n,"p":g,"user":int(u.sum()),"positive_user":int(y[u].sum()),"arms":{},"ties":{}}
    gu=counts["positive_user"]
    nu=counts["user"]
    for a in ARMS:
        m={}
        ties={}
        if a in scores:
            s=np.asarray(scores[a])
            assert np.all((s>=0)&(s<=1))
            order=np.argsort(-s)
            m["auc"]=float(roc_auc_score(y,s)) if 0<g<n else None
        elif a=="uniform":
            m["auc"]=.5 if 0<g<n else None
        else:
            # Each positive in preferred role strictly outranks a negative outside it; ties within role get half credit.
            nuser_neg=nu-gu
            outside_neg=n-nu-(g-gu)
            wins=gu*outside_neg
            equal=gu*nuser_neg+(g-gu)*outside_neg
            m["auc"]=(wins+.5*equal)/(g*(n-g)) if 0<g<n else None
        for b in BUDGET:
            k=math.ceil(b*n)
            key="R"+str(round(b*100))
            if a in scores:
                hits=int(y[order[:k]].sum())
                ties[key]=bool(k<n and s[order[k-1]]==s[order[k]])
            elif a=="uniform":
                hits=k/n*g
            else:
                hits=min(k,nu)*gu/max(1,nu)+max(0,k-nu)*(g-gu)/max(1,n-nu)
            m[key]=float(hits/g) if g else None
        counts["arms"][a]=m
        counts["ties"][a]=ties
    return counts

def aggregates(rows,clusters):
    keys=sorted(rows)
    out={"histories":len(keys),"eligible":sum(x["p"]>0 for x in rows.values()),"means":{},"pairs":{}}
    for a in ARMS:
        out["means"][a]={}
        for m in ("R20","auc","R10","R40"):
            vals=[rows[k]["arms"][a][m] for k in keys if rows[k]["arms"][a][m] is not None]
            out["means"][a][m]=float(np.mean(vals))
    for a,b in PAIRS:
        out["pairs"][a+"-"+b]={}
        for m in out["means"][a]:
            ks=[k for k in keys if rows[k]["arms"][a][m] is not None]
            delta={k:rows[k]["arms"][a][m]-rows[k]["arms"][b][m] for k in ks}
            d=np.array(list(delta.values()))
            per=collections.defaultdict(list)
            for k in ks:
                per[clusters[k]].append(delta[k])
            nc=len(per)
            z=dict(delta=float(np.mean(d)),win=int((d>1e-13).sum()),loss=int((d< -1e-13).sum()),tie=int((abs(d)<=1e-13).sum()),clusters=nc,ci=None)
            if nc>1:
                num=np.array([sum(v) for v in per.values()])
                den=np.array([len(v) for v in per.values()])
                rng=np.random.default_rng(13)
                idx=rng.integers(0,nc,size=(10000,nc))
                z["ci"]=np.quantile(num[idx].sum(axis=1)/den[idx].sum(axis=1),[.025,.975]).tolist()
            out["pairs"][a+"-"+b][m]=z
    return out

def run():
    f=read(HERE/"split.json")["folds"]
    assert len(f)==33
    gold={}
    for p in sorted(HERE.glob("gold-*-of-*.json.gz")):
        a=read(p)
        assert not set(gold)&set(a)
        gold.update(a)
    assert len(gold)==500
    tab={}
    strict=[]
    audit=[]
    for i,fold in enumerate(f):
        rows=read(HERE/f"pred-{i:02d}.json.gz")
        md=read(HERE/f"fold-{i:02d}.json")
        assert hashlib.sha256((HERE/f"pred-{i:02d}.json.gz").read_bytes()).hexdigest()==md["prediction_hash"]
        assert [r["id"] for r in rows]==fold["test"]==md["test"] and fold["train"]==md["train"]
        if fold["section"]=="strict":
            strict+=fold["test"]
        for r in rows:
            k=r["id"]
            assert k not in tab
            u=np.array(r["user"],dtype=bool)
            tab[k]=group(np.array(gold[k]),u,r["score"])
        audit.append(md)
    assert len(tab)==500 and len(strict)==62
    results={"strict":aggregates({k:tab[k] for k in strict},{k:k for k in strict}),
          "all":aggregates(tab,{k:"single_component" for k in tab}),
          "additional":aggregates({k:tab[k] for k in tab if k not in strict},{k:"descriptive" for k in tab})}
    meta={}
    for k in ("strict","additional"):
        v=[x for x in audit if x["section"]==k]
        meta[k]={"folds":len(v),"min_train_hist":min(len(x["train"]) for x in v),"max_train_hist":max(len(x["train"]) for x in v),
                 "min_train_positive":min(x["train_pos"] for x in v),"max_train_positive":max(x["train_pos"] for x in v),
                 "min_train_turn":min(x["train_remaining"] for x in v),"max_train_turn":max(x["train_remaining"] for x in v),
                 "purged_pos_across_fits":sum(x["removed_train_pos"] for x in v),"purged_neg_across_fits":sum(x["removed_train_neg"] for x in v),
                 "degenerate_fits":sum(x["degenerate"] for x in v)}
    save(HERE/"group-metrics.json.gz",tab)
    save(HERE/"results.json",results)
    save(HERE/"audit.json",meta)
    print(json.dumps({k:{"means":v["means"],"primary":v["pairs"]["calibrated-original"]["R20"],"edge":v["pairs"]["edge-shifted"]["R20"]} for k,v in results.items()}))
if __name__=="__main__":
    run()
