"""Create the registered C sample, run blind predictions, then score in a separate command."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
from time import perf_counter

from free_git import (GitObjects,Snapshot,first_path,visible_paths,diverse_paths,compact,
                      as_bytes,adjacency_control,recall)

ROOT=Path(__file__).resolve().parent
SRC=ROOT.parent/"transfer"
METHODS=("blind","direct","one","short","free","edge")
F=("repo","before","after","s","t")


def sha(b): return hashlib.sha256(b).hexdigest()


def dump(obj): return json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()


def run(repo,directory,ks):
    obj=GitObjects(directory)
    logs=[]
    try:
        for k in ks:
            _,old,new,s,t=k
            t0=perf_counter()
            before=Snapshot(obj,old)
            p=first_path(before,s,t)
            if not p: raise RuntimeError("Original registered positive has no path")
            measured=before.describe()
            primary_time=perf_counter()-t0
            original_counts=before.count.copy()
            original_trees=set(before.trees)
            original_blobs=set(before.blobs)
            start=perf_counter()
            paths=visible_paths(before.edges,s,t,16)
            if not paths or p not in paths:
                raise RuntimeError("BFS first path not available from its opened providers")
            paths=[p]+[h for h in paths if h!=p]
            enumerate_elapsed=perf_counter()-start
            caches={}
            cpu={}
            def measured_cache(name,builder,enumerated=False):
                tick=perf_counter()
                caches[name]=builder()
                cpu[name]=perf_counter()-tick+(enumerate_elapsed if enumerated else 0.)
            measured_cache("one",lambda:compact(before,p,[p],[]))
            measured_cache("short",lambda:compact(before,p,paths[:3],[]),True)
            measured_cache("free",lambda:compact(before,p,diverse_paths(paths),[]),True)
            budget=len(as_bytes(caches["free"]))
            measured_cache("edge",lambda:adjacency_control(before,p,budget))
            assert len(as_bytes(caches["edge"]))<=budget
            assert before.count==original_counts and set(before.trees)==original_trees and set(before.blobs)==original_blobs
            answers={"blind":dict(answer=True,fast=None,verified=None,counts={},seconds=0.,
                                  cache_bytes=len(as_bytes([old,s,t,True])))}
            tick=perf_counter()
            sn=Snapshot(obj,new)
            ans=bool(first_path(sn,s,t))
            answers["direct"]=dict(answer=ans,fast=None,verified=None,seconds=perf_counter()-tick,
                                   cache_bytes=0,**sn.describe())
            for method,cache in caches.items():
                tick=perf_counter()
                sn=Snapshot(obj,new)
                ans,fast,valid=recall(sn,cache,control=(method=="edge"))
                answers[method]=dict(answer=ans,fast=fast,verified=valid,seconds=perf_counter()-tick,
                    cache_bytes=len(as_bytes(cache)),cache=cache,construction_seconds=cpu[method],**sn.describe())
            logs.append(dict(key=k,old=measured,initial_seconds=primary_time,alternatives_seen=len(paths),
                path_candidates=paths,answers=answers))
    finally: obj.close()
    out=ROOT/"logs"/(repo+".jsonl.gz")
    out.write_bytes(gzip.compress(b"\n".join(map(dump,logs))+b"\n",mtime=0))
    return repo,len(logs),sha(out.read_bytes())


def sample():
    entries=json.loads((SRC/"input_lock.json").read_text(encoding="utf-8-sig"))
    groups=[]
    for repo,group,*rest in entries:
        assert group=="C"
        source=SRC/"shards"/(repo+".jsonl.gz")
        pool=[]
        for line in gzip.decompress(source.read_bytes()).splitlines():
            if not line:continue
            r=json.loads(line)
            pool.append(tuple(r[field] for field in F))
        keys=sorted(pool,key=lambda k:sha("|".join(("G3-Free-C",*k)).encode()))[:24]
        groups.append(dict(repo=repo,keys=keys,source=sha(source.read_bytes()),
                           mirror=str(SRC/"content_mirrors"/repo)))
    raw=dump(dict(groups=groups,protocol=sha((ROOT/"PROTOCOL.md").read_bytes())))
    loc=ROOT/"sample.lock.json"
    if loc.exists(): assert loc.read_bytes()==raw
    else: loc.write_bytes(raw)
    return groups


def predict():
    groups=sample()
    (ROOT/"logs").mkdir(exist_ok=True)
    started=perf_counter()
    shas={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(run,g["repo"],g["mirror"],g["keys"]) for g in groups]
        for future in as_completed(jobs):
            repo,num,h=future.result();shas[repo]=h;print(repo,num,flush=True)
    lock={"shas":shas,"sample_sha":sha((ROOT/"sample.lock.json").read_bytes()),
          "code":{f:sha((ROOT/f).read_bytes()) for f in ["run_free.py","free_git.py"]},
          "seconds":perf_counter()-started,"python":sys.version,
          "git":subprocess.check_output(["git","--version"],text=True).strip()}
    (ROOT/"predictions.lock.json").write_bytes(dump(lock))


def score():
    lock=json.loads((ROOT/"predictions.lock.json").read_bytes())
    sample=json.loads((ROOT/"sample.lock.json").read_bytes())
    assert lock["sample_sha"]==sha((ROOT/"sample.lock.json").read_bytes())
    metric_rows=[]
    cols=["repo","old","new","s","t","truth","method","old_blob","old_blob_bytes","read_blob","read_blob_bytes",
          "old_tree","new_tree","old_metadata_bytes","new_metadata_bytes","stored_bytes","available_paths",
          "saw_extra","fast","validated","correct","old_time","construction_seconds","read_time"]
    for g in sample["groups"]:
        repo=g["repo"]
        old_ref=SRC/"shards"/(repo+".jsonl.gz")
        assert sha(old_ref.read_bytes())==g["source"]
        ref={tuple(row[f] for f in F):row for line in gzip.decompress(old_ref.read_bytes()).splitlines() if line
             for row in [json.loads(line)]}
        path=ROOT/"logs"/(repo+".jsonl.gz")
        assert lock["shas"][repo]==sha(path.read_bytes())
        for line in gzip.decompress(path.read_bytes()).splitlines():
            if not line: continue
            row=json.loads(line); k=tuple(row["key"]); orig=ref[k]; y=orig["truth"]
            assert row["path_candidates"][0]==orig["one"]["proofs"][0]
            for method in METHODS:
                ans=row["answers"][method]; c=ans["counts"]; b=row["old"]["counts"]
                metric_rows.append(dict(zip(cols,[*k,int(y),method,b.get("blob_objects",0),b.get("blob_bytes",0),
                    c.get("blob_objects",0),c.get("blob_bytes",0),b.get("tree_objects",0),c.get("tree_objects",0),
                    b.get("tree_bytes",0)+b.get("commit_bytes",0),c.get("tree_bytes",0)+c.get("commit_bytes",0),
                    ans["cache_bytes"],row["alternatives_seen"],int(row["alternatives_seen"]>=2),
                    ans.get("fast"),ans.get("verified"),int(int(y)==ans["answer"]),row["initial_seconds"],
                    ans.get("construction_seconds",0.),ans.get("seconds",0.)])))
    with (ROOT/"costs.csv").open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(metric_rows)
    kept=("old_blob","read_blob","old_blob_bytes","read_blob_bytes","old_tree","new_tree","old_metadata_bytes",
          "new_metadata_bytes","stored_bytes","saw_extra","fast","validated","correct","construction_seconds")
    def summary(rs):
        return {m:{"n":sum(r["method"]==m for r in rs),**{
            k:sum((r[k] or 0) for r in rs if r["method"]==m) for k in kept}} for m in METHODS}
    per={g["repo"]:summary([r for r in metric_rows if r["repo"]==g["repo"]]) for g in sample["groups"]}
    comparisons={}
    for method,base in [("free","one"),("free","edge"),("short","free"),("one","direct")]:
        a=[r for r in metric_rows if r["method"]==method];b=[r for r in metric_rows if r["method"]==base]
        ds=[(x["read_blob"]-y["read_blob"]) for x,y in zip(a,b)]
        dep={k:(v[method]["read_blob"]-v[base]["read_blob"])/v[method]["n"] for k,v in per.items() if v[method]["n"]}
        vals=list(dep.values());rng=random.Random(20261118)
        boot=sorted(statistics.mean(rng.choices(vals,k=len(vals))) for _ in range(10000))
        comparisons[method+"-"+base]={"delta_sum":sum(ds),"paired_fewer":sum(x<0 for x in ds),
            "paired_more":sum(x>0 for x in ds),"paired_tied":ds.count(0),"repo_deltas":dep,
            "repo_macro":statistics.mean(vals),"descriptive_cluster_percentile_95":[boot[249],boot[9749]]}
    drows=[r for r in metric_rows if r["method"]=="direct"]
    res={"all":summary(metric_rows),"per_repo":per,"paired":comparisons,
         "negatives":sum(not r["truth"] for r in drows),"distribution_paths":dict(Counter(r["available_paths"] for r in drows))}
    (ROOT/"results.json").write_text(json.dumps(res,indent=2),encoding="utf8")
    for m,a in res["all"].items():print(m,a)
    print(comparisons)
    print(res["distribution_paths"],res["negatives"])


if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="predict":predict()
    elif mode=="score":score()
    else:raise ValueError(mode)
