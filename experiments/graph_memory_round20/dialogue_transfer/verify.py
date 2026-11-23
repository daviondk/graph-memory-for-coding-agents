"""Recompute every group metric, split, overall mean, contrast, confidence interval and SHA."""
import gzip
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path
import numpy as np
from score import load, summary
HERE=Path(__file__).resolve().parent

def check(actual, expected):
    if isinstance(actual,dict):
        assert actual.keys()==expected.keys()
        for k,v in actual.items():
            check(v,expected[k])
    elif isinstance(actual,list):
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected,strict=True):
            check(a,b)
    elif isinstance(actual,float):
        assert abs(actual-expected)<1e-12,(actual,expected)
    else:
        assert actual==expected,(actual,expected)

def auc(y,s):
    positives=sum(y)
    if positives in (0,len(y)):
        return None
    total=0.0
    zeros=0
    for _,members in itertools.groupby(sorted(zip(s,y)),lambda a:a[0]):
        block=[a[1] for a in members]
        pos=sum(block)
        neg=len(block)-pos
        total+=pos*(zeros+neg/2)
        zeros+=neg
    return total/(positives*(len(y)-positives))

def main():
    if (HERE/"MANIFEST.json").exists():
        hashes=json.loads((HERE/"MANIFEST.json").read_bytes())
        assert set(hashes)=={p.name for p in HERE.iterdir() if p.is_file() and p.name not in ("MANIFEST.json","MANIFEST_SHA256.json")}
        for name,dig in hashes.items():
            assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==dig,name
    split=load("split.json.gz")
    chosen=[]
    used=set()
    raw=load("observed-session-ids.json.gz")
    for q,hist in sorted(split["histories"].items()):
        sids=raw[q]
        assert len(hist)==len(sids)
        ids=set()
        for h,rid in zip(hist,sids,strict=True):
            assert h in split["size"] and "i"+rid in split["aliases"][h]
            ids.update(("i"+rid,"c"+h))
        if not used & ids:
            used.update(ids)
            chosen.append(q)
    assert chosen==split["selected"]
    tables=load("group-metrics.json.gz")
    for nm,family in (("external","external"),("domain","within")):
        rows=load(nm+"-forecast.json.gz")
        gold=load(nm+"-gold.json.gz")
        metrics=tables[family]
        assert len(rows)==len(gold)==len(metrics)
        for row in rows:
            k=row["id"]
            y=gold[k]
            assert all(z in (0,1) for z in y)
            assert metrics[k]["p"]==sum(y) and metrics[k]["n"]==len(y)
            for arm,s in row["scores"].items():
                assert len(y)==len(s)
                item={"auc":auc(y,s)}
                ties={}
                perm=np.argsort(-np.asarray(s)).tolist()
                for b in (10,20,40):
                    n=math.ceil((b/100)*len(y))
                    item["R"+str(b)]=sum(y[i] for i in perm[:n])/sum(y) if sum(y) else None
                    ties["R"+str(b)]=n<len(s) and s[perm[n-1]]==s[perm[n]]
                check({"metric":item,"ties":ties},metrics[k]["arms"][arm])
    results=load("results.json")
    a=tables["external"]
    b=tables["within"]
    check(summary(a,list(a),split["components"]),results["external"])
    check(summary(a,chosen,{k:k for k in chosen}),results["disjoint"])
    check(summary(b,list(b),load("domain-groups.json")),results["within"])
    print("PASS. All three models and all 4 metrics from text-free prediction vectors; external and domain; budget ties checked with native ordering.")
if __name__=="__main__":
    main()
