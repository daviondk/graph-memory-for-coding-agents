"""Issue-balanced fixed pairwise ridge. Leave each evaluation repository out of fitting."""
import collections, gzip, hashlib, json, math, random
from pathlib import Path
import numpy as np
from features import BA,LOCAL,LINK
HERE=Path(__file__).resolve().parent
GROUPS={"flat":BA,"decl":BA+LOCAL,"graph":BA+LOCAL+LINK,"placebo":BA+["perm_"+a for a in LOCAL+LINK]}
def stats(rows,model,other,label="any",metric="hit"):
    vals=[r["arms"][model][label][metric]-r["arms"][other][label][metric] for r in rows]
    rep=collections.defaultdict(list)
    for v,r in zip(vals,rows):rep[r["repo"]].append(v)
    names=sorted(rep);ss=np.array([sum(rep[k]) for k in names]);nn=np.array([len(rep[k]) for k in names])
    rng=np.random.default_rng(20261118);xx=rng.integers(0,len(nn),(20000,len(nn)))
    ci=np.quantile(ss[xx].sum(axis=1)/nn[xx].sum(axis=1),[.025,.975]).tolist()
    w=sum(v>0 for v in vals);l=sum(v<0 for v in vals);d=w+l
    p=min(1.,sum(math.comb(d,j) for j in range(min(w,l)+1))*2/(2**d)) if d else 1.
    return {"n":len(rows),"delta":sum(vals)/len(rows),"ci":ci,"w":w,"l":l,"ties":len(rows)-d,"p":p,
            "per_repo":{k:sum(rep[k]) for k in names}}
def main():
    labels=json.loads((HERE/"labels.json").read_text())
    records=[json.loads(s) for s in gzip.decompress((HERE/"features.jsonl.gz").read_bytes()).splitlines() if s]
    # Sufficient statistics per query; no global normalization using test labels or future points.
    matrices={}; sufficient={}
    for ri,r in enumerate(records):
        g=labels[r["source"]][r["id"]]
        for a,keys in GROUPS.items():
            mat=np.array([[v[k] for k in keys] for v in r["features"]],dtype=float).reshape(-1,len(keys))
            matrices[ri,a]=mat
            for target in ["any","single"]:
                pos=[i for i,p in enumerate(r["paths"]) if p in g[target]]
                neg=[i for i,p in enumerate(r["paths"]) if p not in g[target]]
                if not pos or not neg or r["excluded"]:continue
                diff=np.array([mat[i]-mat[j] for i in pos for j in neg])
                sufficient[ri,a,target]=(diff.T@diff/len(diff),diff.mean(axis=0))
    outputs=[];coeflog={};oracle={}
    for panel,predict,train,timecut,target in [("loc_loro","loc","loc",False,"any"),("loc_time","loc","loc",True,"any"),
                                                ("river_zero","river","loc",False,"any"),("river_zero_time","river","loc",True,"any"),
                                                ("river_loro","river","river",False,"any"),("river_time","river","river",True,"any"),
                                                ("river_loro_single","river","river",False,"single")]:
        fits={}
        for ri,r in enumerate(records):
            if r["source"]!=predict:continue
            cachekey=r["repo"]+"|"+(r["date"] if timecut else "all")
            if cachekey not in fits:
                elig=[j for j,n in enumerate(records) if n["source"]==train and n["repo"]!=r["repo"] and (not timecut or n["date"]<r["date"])]
                fit={}
                for a,keys in GROUPS.items():
                    moments=[sufficient[j,a,target] for j in elig if (j,a,target) in sufficient]
                    n=len(moments)
                    if n>=15:
                        gram=sum(t[0] for t in moments)/n+.02*np.eye(len(keys));rhs=sum(t[1] for t in moments)/n
                        beta=np.linalg.solve(gram,rhs)
                    else:
                        beta=np.zeros(len(keys));beta[0]=1.
                    fit[a]=beta;coeflog[panel+"|"+cachekey+"|"+a]={"n":n,"weights":dict(zip(keys,beta.tolist()))}
                fits[cachekey]=fit
            fit=fits[cachekey];pred={"native":r["paths"]}
            for a in GROUPS:
                value=matrices[ri,a]@fit[a]
                ix=list(range(len(value))) if r["excluded"] else sorted(range(len(value)),key=lambda n:(-value[n],n))
                pred[a]=[r["paths"][j] for j in ix]
            g=labels[predict][r["id"]]
            def metrics(ls,t):
                hits=[i for i,p in enumerate(ls,1) if p in set(t)]
                return {"hit":int(1 in hits),"mrr":1/min(hits) if hits else 0.}
            arms={a:{k:metrics(ps,t) for k,t in g.items()} for a,ps in pred.items()}
            outputs.append({"id":r["id"],"repo":r["repo"],"panel":panel,"arms":arms,"rankings":pred,"native_n":len(r["paths"]),
                            "oracle":int(bool(set(g["any"])&set(r["paths"])))})
    result={}
    for panel in sorted({r["panel"] for r in outputs}):
        rows=[r for r in outputs if r["panel"]==panel]
        arms=list(rows[0]["arms"])
        result[panel]={"n":len(rows),"groups":len({r["repo"] for r in rows}),"oracle":sum(r["oracle"] for r in rows),
                       "totals":{a:{k:{m:sum(r["arms"][a][k][m] for r in rows) for m in ["hit","mrr"]}
                                    for k in ["any","single","patch"]} for a in arms},
                       "pair":{a+"-"+b:stats(rows,a,b) for a,b in [("graph","native"),("graph","flat"),("graph","decl"),
                                                                     ("graph","placebo"),("decl","flat"),("flat","native")]}}
        z=result[panel]
        print(panel,z["n"],z["oracle"],{a:v["any"]["hit"] for a,v in z["totals"].items()},
              [z["pair"]["graph-flat"][k] for k in ("w","l","ci")])
    (HERE/"results.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    (HERE/"score_rows.jsonl.gz").write_bytes(gzip.compress(("\n".join(json.dumps(r,separators=(",",":")) for r in outputs)+"\n").encode(),mtime=0))
    (HERE/"coefficients.json.gz").write_bytes(gzip.compress(json.dumps(coeflog,sort_keys=True,separators=(",",":")).encode(),mtime=0))
if __name__=="__main__":main()

