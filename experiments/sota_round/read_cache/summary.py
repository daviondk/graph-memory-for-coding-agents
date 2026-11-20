"""Read-cache census, paired repository bootstrap and storage costs."""
import csv
import gzip
import json
import os
import random
from collections import Counter,defaultdict
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from run import ARMS,HERE


def data(name):
    with gzip.open(HERE/name,"rt",encoding="utf8") as f:
        yield from map(json.loads,f)


def main():
    groups=defaultdict(Counter)
    total=Counter()
    arms={a:Counter() for a in ARMS}
    peaks=Counter()
    active,repeat=set(),set()
    for h in data("histories.jsonl.gz"):
        total.update(h["counts"])
        g=groups[h["repo"]]
        g["n"]+=h["counts"].get("eligible",0)
        if h["counts"].get("eligible"):
            active.add(h["sid"])
        if h["counts"].get("repeated_eligible_key"):
            repeat.add(h["sid"])
        for a,metrics in h["arms"].items():
            peaks[a]=max(peaks[a],metrics["peak"])
            arms[a].update({k:v for k,v in metrics.items() if k!="peak"})
            for k in ("correct","stale","miss","unknown"):
                g[a+"_"+k]+=metrics.get(k,0)
    # Independent aggregation of per-query recorded decisions including missing labels.
    audited={a:Counter() for a in ARMS}
    touched={}
    for q in data("queries.jsonl.gz"):
        assert len(q["arms"])==len(ARMS)
        for a,choice in zip(ARMS,q["arms"]):
            if choice is not None:
                fill,slot,state=choice
                origin=touched[(q["sid"],fill,slot)]
                assert fill<q["b"] and origin["writable"] and origin["cmd_sha256"]==q["cmd_sha256"]
                same=(origin["rc"],origin["stdout_sha256"])==(q["rc"],q["stdout_sha256"])
                expected="unknown" if q["rc"] is None or q["stdout_sha256"] is None else ("correct" if same else "stale")
                assert state==expected
            else:
                state="miss"
            audited[a][state]+=1
        # Keys are scoped by history. An episode can restart the assistant index.
        touched[(q["sid"],q["b"],q["slot"])]=q
    summary={}
    for a,m in arms.items():
        for k in ("correct","stale","miss","unknown"):
            assert m[k]==audited[a][k]
        assert sum(audited[a].values())==total["eligible"]
        served=m["correct"]+m["stale"]+m["unknown"]
        summary[a]={**m,"served":served,"peak_bytes":peaks[a],
                    "mean_end_batch_bytes":m["sum_batch_end_bytes"]/total["batches"],
                    "stale_fraction_per_scored_hit":m["stale"]/(served-m["unknown"]) if served>m["unknown"] else None}
    repos=sorted(groups)
    rng=random.Random(20261116)
    weights=np.zeros((10000,len(repos)),dtype=np.int64)
    for i in range(len(weights)):
        weights[i]=np.bincount(rng.choices(range(len(repos)),k=len(repos)),minlength=len(repos))
    ns=weights @ np.array([groups[r]["n"] for r in repos])
    assert len(repos)==90 and np.all(ns>0)
    contrasts={}
    for a in ARMS:
        if a=="selective":
            continue
        contrast={}
        for metric in ("correct","stale","unknown"):
            ds=np.array([groups[r][f"selective_{metric}"]-groups[r][f"{a}_{metric}"] for r in repos])
            rates=(weights@ds)*1000/ns
            contrast[metric]={"delta_count":int(sum(ds)),"per_1000":float(sum(ds)*1000/total["eligible"]),
                              "ci95":np.quantile(rates,[.025,.975]).tolist()}
        contrasts[a]=contrast
    equal=[a for a in ARMS if not arms[a]["stale"] and not arms[a]["unknown"]]
    out={"counts":total,"histories_with_queries":len(active),"histories_with_repeats":len(repeat),
         "repos_with_queries":sum(bool(g["n"]) for g in groups.values()),"arms":summary,
         "observed_zero_stale_and_zero_unknown":equal,
         "max_correct_at_zero":max((arms[a]["correct"] for a in equal),default=None),
         "selective_minus_comparator":contrasts,"numpy":np.__version__}
    (HERE/"summary.json").write_text(json.dumps(out,indent=2),encoding="utf8")
    keys=sorted(set().union(*(x.keys() for x in groups.values())))
    with (HERE/"repositories.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.writer(f);w.writerow(["repo",*keys])
        for repo in repos:
            w.writerow([repo,*(groups[repo][k] for k in keys)])
    print("eligible",total["eligible"],"repeats",total["repeated_eligible_key"])
    for a in ARMS:
        print(a,dict(audited[a]))


if __name__=="__main__":
    main()
