"""Audit public multi-seed receipts, rank permutations, averages and final paired bootstrap."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean, stdev
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
SEEDS=(13,17,29,37,41)
METRICS=("coverage_512","coverage_1024","coverage_2048","full_support_2048","recall_5","mrr","coverage_auc","full_support_auc")
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as fp:return hashlib.file_digest(fp,"sha256").hexdigest()
def close(x,y):assert abs(x-y)<1e-11,(x,y)
def main():
    plan=load(HERE/"plan.json");assert all(sha(WORK/n)==h for n,h in plan["files"].items())
    assert plan["code"]=={n:sha(HERE/(n+".py")) for n in ("study","score")}
    assert list(SEEDS)==plan["seeds"]
    s=[seed for seed in SEEDS if (HERE/f"seed-{seed}/results.json").exists()]
    assert s and s[0]==13
    out={};hashes={};distributions={}
    for seed in s:
        d=HERE/f"seed-{seed}";receipts=load(d/"results.json")
        assert receipts["seal"]==sha(d/"forecast-seal.json") and receipts["q_sha"]==sha(d/"metrics.json.gz")
        seal=load(d/"forecast-seal.json")
        assert seal["code"]==sha(HERE/"score.py") and seal["plan"]==sha(HERE/"plan.json")
        if seed!=13:
            m=load(d/"model.json");p=load(d/"pairs.json");c=load(d/"calibration.json")
            assert c["weights"]==sha(d/"model.json") and c["source"]==sha(WORK/"graph_memory_round20/residual_graph/cpu_fallback/cohorts.json")
            assert len(set(c["queries"]))==101 and c["source"] and c["rows"]==10702
            assert p["pairs"]==sha(d/"train-pairs.json.gz") and m["input_pairs"]==p["pairs"]
            assert p["config"]["random_seed"]==m["settings"]["trainer"]["random_seed"]==seed
            assert m["train"]==3894 and m["dev"]==500 and load(d/"embeddings.json")["checkpoint"]==m["files"]["model.safetensors"]
        ids=set();trajectories=set()
        for i,r in enumerate(seal["receipts"]):
            path=d/r["file"];source=WORK/f"graph_memory_round19/trained_rank/forecasts-main-{i}.json.gz"
            assert sha(path)==r["sha"] and sha(source)==r["source"]
            index={row["q"]:(row["t"],len(row["rr"])) for row in load(source)}
            for row in load(path):
                t,n=index.pop(row["q"])
                assert t==row["t"] and sorted(row["dense"])==sorted(row["factor"])==list(range(n)) and row["q"] not in ids
                ids.add(row["q"]);trajectories.add(t)
            assert not index
        assert len(ids)==2000 and len(trajectories)==1207
        res=load(d/"metrics.json.gz")
        for a,rows in res.items():
            assert set(rows)==ids
            for k in METRICS:close(mean(v[k] for v in rows.values()),receipts["summary"][a][k])
        out[seed]=res;hashes[str(seed)]=sha(d/"results.json")
    if 13 in s:
        historical=load(WORK/"graph_memory_round20/factor_reader/metrics-test-rows.json.gz")
        assert out[13]["dense"]==historical["dense"] and out[13]["factor"]==historical["factor"]
    target=HERE/("five-seed-results.json" if len(s)==5 else f"interim-{len(s)}-results.json")
    summary=load(target);assert summary["seeds"]==s and summary["results"]==hashes
    q0=sorted(out[s[0]]["dense"])
    cluster=defaultdict(list)
    for q in q0:
        t=out[s[0]]["dense"][q]["t"]
        cluster[t].append(np.array([[out[seed]["factor"][q][m]-out[seed]["dense"][q][m] for m in METRICS] for seed in s]).mean(axis=0))
    group=[cluster[t] for t in sorted(cluster)];n=np.array([len(rows) for rows in group]);a=np.array([np.sum(rows,axis=0) for rows in group])
    rng=np.random.default_rng(13);boot=[]
    for _ in range(100):
        ix=rng.integers(0,len(n),size=(100,len(n)));boot.extend(a[ix].sum(axis=1)/n[ix].sum(axis=1)[:,None])
    for k,m in enumerate(METRICS):
        calc=[a[:,k].sum()/n.sum(),*np.quantile(np.asarray(boot)[:,k],[.025,.975])]
        for x,y in zip(calc,summary["paired"][m],strict=True):close(x,y)
        for arm in ("dense","factor"):
            means=[mean(out[seed][arm][q][m] for q in q0) for seed in s]
            close(mean(means),summary["summary"][arm][m]["mean"])
            if len(s)>1:close(stdev(means),summary["summary"][arm][m]["sd"])
    print("Verified",len(s),"complete seeds, 2000 questions, 1207 trajectories, both full permutations, eight metrics and paired trajectory resampling.")
if __name__=="__main__":main()

