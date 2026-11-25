"""Replicate the ISETrace 2x2 with a public document as the openable object."""
from collections import Counter,defaultdict
from functools import lru_cache
import os
from pathlib import Path
import sqlite3
import sys

D=Path(__file__).resolve().parent
T=D.parent/"transfer";sys.path.insert(0,str(T))
import common as c
sys.path.append(str(D.parent/"field_first"))
from decide import rank,visible,paid_open
import numpy as np
from scipy.stats import binomtest
NAMES=("anchor/first","anchor/lex","lex/first","lex/lex")
def merged(scopes):
    by=defaultdict(list)
    for j,(d,a,b) in enumerate(scopes):by[d].append((a,b,j))
    out=[]
    for d,parts in by.items():
        spans=[]
        for a,b,j in sorted(parts):
            if spans and spans[-1][2]>=a:
                assert spans[-1][2]==a
                spans[-1][2]=b;spans[-1][3]=min(spans[-1][3],j)
            else:spans.append([d,a,b,j])
        out.extend(spans)
    new=[r[:3] for r in sorted(out,key=lambda r:r[3])]
    assert sum(b-a for d,a,b in new)==sum(b-a for d,a,b in scopes)
    return new
def predict():
    assert c.checksum(D/"PROTOCOL_RU.md")=="a0a8d3d723cc5709df69a883b0eefd0447d1d1f5c44513baa91a5eb465713168"
    predfile=T/"predictions.json.gz";source=c.read(T/"forecast-seal.json")
    assert c.checksum(predfile)==source["forecasts"]
    v=c.get_views();tok=c.tok();qm={r[0]:r[2] for r in v["q"]}
    docs={j:r[2] for j,r in enumerate(v["documents"])}
    tables=c.CACHE/"source-lookup.sqlite"
    if not tables.exists():
        temp=tables.with_suffix(".stage")
        conn=sqlite3.connect(temp)
        conn.execute("CREATE TABLE source(d INTEGER PRIMARY KEY,body TEXT)")
        with conn:conn.executemany("INSERT INTO source VALUES(?,?)",docs.items())
        conn.close();os.replace(temp,tables)
    conn=sqlite3.connect(tables.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    assert len(docs)==conn.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    records=[]
    for row in c.read(predfile):
        q=row["q"];prior=row["arms"]["two_ratio"]
        units=[v["blocks"][i] for i in prior["chosen"]]
        frozen="\n".join(c.render(b,v["documents"]) for b in units)
        assert c.sha(frozen.encode())==prior["text_sha"]
        scopes=[[u["doc"],u["a"],u["b"]] for u in units]
        r={"q":q,"source_tokens":prior["tokens"],"arms":{}}
        for fmt,parts in (("merged",merged(scopes)),("separate",scopes)):
            windows=visible(parts,docs,tok);order=rank(windows,qm[q]);best=order[0]
            for name,start in (("anchor",0),("lex",best)):
                doc=windows[start][0]
                first=next(i for i,z in enumerate(windows) if z[0]==doc)
                best_local=next(i for i in order if windows[i][0]==doc)
                for attr,k in (("first",first),("lex",best_local)):
                    e,l=windows[k][:2]
                    found=conn.execute("SELECT body FROM source WHERE d=?",(e,)).fetchone()
                    assert found and found[0]==docs[e]
                    d,a,b,n=paid_open(tok,found[0],e,l)
                    text=f"[{d}:{a}] "+docs[d][a:b]
                    assert n==len(tok.encode(text,add_special_tokens=False).ids)<=256
                    r["arms"][f"{fmt}/{name}/{attr}"]=[d,a,b,n,c.sha(text.encode())]
        records.append(r)
    conn.close()
    checks=c.save(D/"opens.json.gz",records)
    print("sealed",c.save(D/"open-lock.json",dict(opens=checks,source=c.checksum(predfile),plan=c.checksum(D/"PROTOCOL_RU.md"),
         file_table=c.checksum(tables),select_count=len(records)*8,code=c.checksum(Path(__file__)),
         rank=c.checksum(D.parent/"field_first/decide.py"),open_source=c.checksum(D.parent/"address_open/choose.py"))))

def inference(diffs,clusters):
    d=np.array(diffs,dtype=float);groups,ix=np.unique(clusters,return_inverse=True)
    sums=np.bincount(ix,weights=d);counts=np.bincount(ix)
    ng=len(groups);rng=np.random.default_rng(23091);batches=[]
    for _ in range(200):
        draw=rng.integers(0,ng,size=(100,ng));batches.extend(sums[draw].sum(axis=1)/counts[draw].sum(axis=1))
    return dict(delta_pp=float(d.mean()*100),clusters=ng,boot95_pp=(np.quantile(batches,[.025,.975])*100).tolist())

def score():
    import runpy
    evaluator=runpy.run_path(str(T/"score.py"),run_name="transfer_evaluator")
    v=c.get_views();seal=c.read(D/"open-lock.json");assert c.checksum(D/"opens.json.gz")==seal["opens"]
    goal,_=evaluator["labels"](v)
    per=[]
    for row in c.read(D/"opens.json.gz"):
        spans,reason=goal[row["q"]];assert not reason
        gold=evaluator["union"](spans);target={x[0] for x in gold};assert len(target)==1
        size=sum(b-a for _,a,b in gold)
        r={"q":row["q"],"doc":int(next(iter(target))),"source_tokens":row["source_tokens"],"arms":{}}
        for name,(d,a,b,n,_) in row["arms"].items():
            overlap=evaluator["overlap"](gold,[(d,a,b)])
            r["arms"][name]=dict(full=int(overlap==size),reference_doc=int(d in target),coverage=overlap/size,tokens=n)
        per.append(r)
    keys=per[0]["arms"]
    primary=[]
    for fmt in ("merged","separate"):
        lhs=fmt+"/anchor/lex";rhs=fmt+"/anchor/first"
        diff=[x["arms"][lhs]["full"]-x["arms"][rhs]["full"] for x in per]
        wins=diff.count(1);losses=diff.count(-1)
        primary.append(dict(format=fmt,wins=wins,losses=losses,
            paired_mcnemar=float(binomtest(wins,wins+losses).pvalue) if wins+losses else 1.,
            dialogue=inference(diff,[x["q"] for x in per]),doc=inference(diff,[x["doc"] for x in per])))
    res={name:{k:float(np.mean([r["arms"][name][k] for r in per])) for k in per[0]["arms"][name]} for name in keys}
    raw=c.save(D/"outcomes.json.gz",per)
    print("results",c.save(D/"results.json",dict(n=len(per),metrics=res,source_tokens=float(np.mean([r["source_tokens"] for r in per])),
             prior=c.checksum(D/"open-lock.json"),per_query=raw,contrasts=primary)))
    print(res);print(primary)

if __name__=="__main__":
    globals()[sys.argv[1]]()
