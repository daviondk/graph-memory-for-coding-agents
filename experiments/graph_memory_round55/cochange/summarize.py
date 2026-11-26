"""Aggregate chronological event logs and preserve repository-level units."""
from collections import Counter
import argparse
import hashlib
from pathlib import Path
from statistics import mean
from extract import HERE, read_json, write_json

def summary(blocks):
    first = blocks[0]
    pol = first["policies"]
    assert all(b["policies"] == pol for b in blocks)
    events = [e for block in blocks for e in block["events"]]
    res = {"evaluated_commits": len(events), "update": list(map(sum, zip(*(e[1] for e in events)))),
           "costs": {}, "prediction": {}}
    for i, name in enumerate(pol):
        res["costs"][name] = {"cold": list(map(sum, zip(*(b["cold"][name][:2] for b in blocks)))),
                              "warm": list(map(sum, zip(*(e[2][i] for e in events))))}
    for typ, k in (("unconditional", 3), ("conditional", 4)):
        actual = [e[k] for e in events if e[k] is not None]
        if not actual:
            continue
        result = {"n":len(actual), "mean_availability": mean(a[1]/a[0] for a in actual),
                  "mean_target_size": mean(a[0] for a in actual), "metrics": {}}
        for j,r in enumerate(("degree","frequency","recency","anchored"), 2):
            result["metrics"][r] = {"hit": sum(a[j] > 0 for a in actual), "recall":mean(a[j]/a[0] for a in actual)}
        res["prediction"][typ] = result
    return res

def main(check):
    streams = read_json(HERE/"commits.json.gz")
    raw = read_json(HERE/"events.json.gz")
    results = {"workload":{}, "results": {}}
    for name, s in streams.items():
        r = s["revisions"]
        results["workload"][name] = {"commits":len(r), "scored":len(r)-64, "giant_after_warmup":sum(len(p)>64 for _,p in r[64:]),
                                     "giant_all":sum(len(p)>64 for _,p in r),
                                     "zero_after_warmup": sum(not p for _,p in r[64:]),
                                     "max_paths":max(len(p) for _,p in r)}
    for w, projects in raw["windows"].items():
        results["results"][w] = {"pooled":summary(list(projects.values())),
                                 "projects":{p:summary([b]) for p,b in projects.items()}}
    write_json(HERE/"results.json", results, check)
    for w, s in results["results"].items():
        g=s["pooled"]
        print(w, g["evaluated_commits"],g["update"], {k:v["warm"] for k,v in g["costs"].items()})
        for t, p in g["prediction"].items():
            print(t, p)
    for p,s in results["results"]["32"]["projects"].items():
        print(p,s["costs"]["classic9"],s["costs"]["partial8"],s["prediction"]["conditional"])
    print("population:",results["workload"])

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    main(ap.parse_args().verify)
