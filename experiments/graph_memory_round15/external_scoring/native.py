"""Apply pinned original evaluation functions to sealed prefix memories with explicit revision audits."""
import collections
import gzip
import hashlib
import importlib.util
import json
import random
import sys
import urllib.request
from pathlib import Path
from statistics import mean
from pyarrow import parquet
from views import ROOT, HOME, load, save, sha

CACHE=Path("D:/CodexResearch/x20-round15-external-scoring")
IG="https://raw.githubusercontent.com/mohammad-nour-alawad/IssueLoc-bench/bd546b8ec1067eb4690cc0677a05320e88e35ff4/"
SW="https://raw.githubusercontent.com/Qiushao-E/SWE-Explore-Bench/5602f031f2d9562d0a805f83402b536e831a5a11/"
def fetch(rel,uri):
    dest=CACHE/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():dest.write_bytes(urllib.request.urlopen(uri,timeout=50).read())
    return {"uri":uri,"sha256":sha(dest.read_bytes())}
def setup():
    sources={}
    sources["localization_bench/common.py"]=fetch("localization_bench/common.py",IG+"localization_bench/common.py")
    for name in ("__init__.py","io.py","usage.py","evaluator.py","metrics.py"):
        path="localization_eval/"+name;sources[path]=fetch("localization_bench/"+path,IG+"localization_bench/"+path)
    for path,uri in {"issue-gold.jsonl":IG+"issueloc_bench_manifest/labels/transformed_swe_bench.jsonl",
                      "swe_eval.py":SW+"eval.py","build_commit_map.py":SW+"build_commit_map.py"}.items():sources[path]=fetch(path,uri)
    save("native-source.json",sources)
    sys.path.insert(0,str(CACHE))
def paired(rows,met):
    groups=collections.defaultdict(list)
    for r in rows:
        groups[r["repo"]].append(r["metrics"]["graph"][met]-r["metrics"]["recent"][met])
    rng=random.Random(277)
    sims=[]
    for _ in range(2000):
        sample=[v for key in rng.choices(list(groups),k=len(groups)) for v in groups[key]]
        sims.append(mean(sample))
    sims.sort()
    return {"metric":met,"diff":mean(v for vs in groups.values() for v in vs),"repository_cluster_ci":[sims[49],sims[1949]],"repositories":len(groups)}
def main():
    for n,h in load(ROOT/"views-seal.json")["files"].items():assert sha((ROOT/n).read_bytes())==h
    forecasts=load(ROOT/"published-forecast.gz")
    setup()
    from localization_bench.localization_eval import evaluator,metrics
    from swe_eval import ExploreEvaluator
    verified=HOME/"graph_memory_round3/real_swe/official_verified.parquet"
    bases={r["instance_id"]:r["base_commit"] for r in parquet.read_table(verified,columns=["instance_id","base_commit"]).to_pylist()}
    source_rev={};srclocks=load(HOME/"graph_memory_round11/readback/input-lock.json")["sources"]
    for name,h in srclocks.items():
        f=HOME/name
        assert sha(f.read_bytes())==h
        with gzip.open(f,"rt",encoding="utf8") as lines:
            for l in lines:
                row=json.loads(l)
                if row["instance"] in forecasts:
                    source_rev[row["instance"]]=row["base_commit"]
    assert set(source_rev)==set(forecasts)
    gold=[json.loads(l) for l in (CACHE/"issue-gold.jsonl").read_bytes().splitlines()]
    labels={r["repo"].lower().replace("/","__")+"-"+str(r["pr_number"]):r for r in gold}
    exp=ExploreEvaluator(CACHE/"swe-explore.jsonl")
    ms=["precision","recall","f1_score","hit_file_rate","ndcg_at_100","recall_at_100","first_useful_hit"]
    rows=[];scope={};native_aggregates={}
    for tag in ("issueloc","sweexplore"):
        overlap=sorted(set(forecasts)&(set(labels) if tag=="issueloc" else set(exp.bench_data_dict)))
        counts=collections.Counter()
        batch={}
        if tag=="sweexplore":
            for a in ("first","recent","repeated","graph"):
                batch[a]=exp.evaluate(lambda _q,i:forecasts[i]["arms"][a]["regions"],overlap,ms)
        else:
            ix={(labels[i]["instance_id"],None):labels[i] for i in overlap}
            for arm in ("first","recent","repeated","graph"):
                predictions=[{"instance_id":labels[i]["instance_id"],"predicted_files":forecasts[i]["arms"][arm]["files"]} for i in overlap]
                native_aggregates[arm]=evaluator.evaluate_localization(ix,predictions)
        for iid in overlap:
            f=forecasts[iid]
            entry=(labels[iid] if tag=="issueloc" else exp.bench_data_dict[iid])
            version=(entry["commit_sha"] if tag=="issueloc" else bases.get(iid))
            exact=(version==source_rev[iid])
            counts["paired"]+=1;counts["base_equal"]+=int(exact);counts["with_views"]+=bool(f["number_of_views"])
            if tag=="sweexplore":
                counts["unbounded_core_regions"]+=sum(r["start"]<1 or r["end"]<1 for r in entry["ground_truth"]["read_core_regions"])
            row={"id":iid,"panel":tag,"repo":f["repo"],"source_panel":f["panel"],"base_equal":exact,
                 "author_commit":version,"archive_commit":source_rev[iid],"with_view":bool(f["number_of_views"]),"metrics":{}}
            for a,output in f["arms"].items():
                if tag=="issueloc":
                    pred,g=metrics.prepare_files_for_scoring(output["files"],entry["gold_files"],ignore_md_changes=False)
                    vals={"hit1":metrics.hit_at_k(pred,g,1),"hit3":metrics.hit_at_k(pred,g,3),"mrr":metrics.reciprocal_rank(pred,g)}
                else: vals=batch[a][iid]
                row["metrics"][a]=vals
            rows.append(row)
        scope[tag]=counts
    summary={}
    for tag in scope:
        summary[tag]={}
        for name,chosen in {"all":[r for r in rows if r["panel"]==tag],
                            "exact":[r for r in rows if r["panel"]==tag and r["base_equal"]],
                            "with_view":[r for r in rows if r["panel"]==tag and r["with_view"]],
                            "kimi_only":[r for r in rows if r["panel"]==tag and "kimi" in r["source_panel"]]}.items():
            if not chosen:continue
            arm_scores={a:{m:mean(r["metrics"][a][m] for r in chosen) for m in chosen[0]["metrics"][a]} for a in chosen[0]["metrics"]}
            met="hit1" if tag=="issueloc" else "precision"
            summary[tag][name]={"n":len(chosen),"means":arm_scores,"contrast":paired(chosen,met)}
    save("external-scores.gz",rows)
    save("official-aggregate.json",native_aggregates)
    save("results.json",{"scope":scope,"groups":summary,"swe_verified_file_sha":sha(verified.read_bytes())})
    print(json.dumps(scope),[(tag,{a:round(list(m.values())[0],4) for a,m in val["all"]["means"].items()}) for tag,val in summary.items()])
if __name__=="__main__":main()
