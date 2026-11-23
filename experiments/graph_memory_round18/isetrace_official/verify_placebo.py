"""Check all precommitted placebo selections and seed outcomes offline with the standard library."""
from collections import Counter
import gzip
import json
from statistics import mean
from verify_package import D, data, evaluate, hashed

def main():
    for manifest in ("placebo-plan.json","placebo-forecast-lock.json","forecast-lock.json","MANIFEST_SHA256.json"):
        if not (D/manifest).exists():
            assert manifest=="MANIFEST_SHA256.json"
            continue
        files=data(manifest)
        if manifest=="forecast-lock.json":files=files["forecasts"]
        for path,h in files.items():assert hashed(D/path)==h,path
    results=data("placebo-results.json");truth=data("gold-spans.json.gz");total=0
    # The exclusion list is included in this package for a standalone audit of the sensitivity population.
    fresh=set(truth)-set(data("sensitivity-excluded-ids.json"))
    assert len(fresh)==1795
    met={}
    for i in range(8):
        extras=data(f"placebo-forecasts-{i}.json.gz")
        with gzip.open(D/f"forecasts-shard-{i}.jsonl.gz","rb") as records:
            for line in records:
                item=json.loads(line);t=item["trajectory_id"]
                for q,views in item["queries"].items():
                    v=views["provenance"];pool={n["node_id"]:n for n in v["ranked"]};ids=sorted(pool)
                    prefix=tuple(v["arms"]["prefix"]);real=tuple(v["arms"]["related"])
                    cache={}
                    def metrics(selected):
                        if selected not in cache:
                            assert len(set(selected))==len(selected)
                            nodes=[pool[k] for k in selected];cost=sum(n["token_count"] for n in nodes)
                            assert cost<=2048
                            cache[selected]=(*evaluate(truth[q],[s for n in nodes for s in n["source_spans"]]),cost)
                        return cache[selected]
                    f=metrics(real)[0]
                    for mode,alternate in extras[t]["queries"][q].items():
                        assert len(alternate)==16
                        for seed,idx in enumerate(alternate):
                            use=prefix+tuple(ids[j] for j in idx);h,c,d,tokens=metrics(use)
                            for label in (("all","no_previous_trajectories") if q in fresh else ("all",)):
                                key=(label,mode,seed)
                                if key not in met:met[key]=Counter()
                                x=met[key];x["n"]+=1;x["h"]+=h;x["coverage"]+=c;x["density"]+=d;x["tokens"]+=tokens
                                x["wins"]+=int(f>h);x["losses"]+=int(f<h);x["changed"]+=int(set(use)!=set(real))
                            total+=1
    assert total==64000
    for label in ("all","no_previous_trajectories"):
        for mode in ("strict","event_degree"):
            summary=results[label][mode]
            m=[]
            for part in summary["per_seed"]:
                x=met[label,mode,part["seed"]];m.append(x)
                assert x["n"]==summary["n"] and x["h"]==part["full_count"]
                assert all(x[key]==part[key] for key in ("changed","wins","losses"))
                assert abs(x["tokens"]/x["n"]-part["tokens"])<1e-10
            for key,col in (("full_support","h"),("coverage","coverage"),("density","density"),("tokens","tokens")):
                assert abs(mean(s[col]/s["n"] for s in m)-summary["placebo"][key])<1e-10
    print("verified",total,"placebo task/seeds, all 4 populations and aggregate citation metrics")
if __name__=="__main__":main()
