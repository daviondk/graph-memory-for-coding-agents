"""Replay shared candidates and exact anchor exposures for seven historical rankings."""
import argparse
from collections import Counter, defaultdict
from heapq import nlargest
from pathlib import Path
import random
from statistics import mean
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from extract import read_json, write_json

METHODS = ("frequency", "degree32", "local16", "local32", "accumulated", "last8anchor", "sample8anchor")
K = 8

def unique_ids(paths, ids):
    for p in paths:
        if p not in ids:
            ids[p] = len(ids)
    return [ids[p] for p in paths]

def score_anchor(anchor, target, ids, previous, t, freq, degree, rows):
    # A query supplies exactly one path string and no other current information.
    anchor_id = ids.get(anchor, -1)
    pool = [i for i in range(len(ids)) if i != anchor_id]
    incident = previous.get(anchor_id, [])
    recent = [j for j in incident if j >= t-32]
    sampled = sorted(incident, key=lambda j: rows[j][0])[:8]
    cases = {"local16": [j for j in recent if j >= t-16], "local32": recent,
             "accumulated": incident, "last8anchor": incident[-8:], "sample8anchor": sampled}
    profiles = {name: Counter(i for j in js for i in rows[j][1]) for name, js in cases.items()}
    profiles["degree32"] = degree
    profiles["frequency"] = freq
    target_ids = {ids.get(p, -1) for p in target if p != anchor}
    hits, work = [], []
    for name in METHODS:
        scores = profiles[name]
        rank = nlargest(K, pool, key=lambda i: (scores[i], freq[i], -i))
        hits.append(len(target_ids.intersection(rank)))
        work.append(len(cases[name]) if name in cases else 0)
    return hits, work

def replay(rows):
    ids = {}
    previous = defaultdict(list)
    indexed = []
    freq, degree = Counter(), Counter()
    result = []
    for t,(rev,names) in enumerate(rows):
        paths = names if len(names) <= 64 else []
        if t >= 64 and len(paths) >= 2:
            chosen = int(rev,16) % len(paths)
            joint = [score_anchor(p, paths, ids, previous, t, freq, degree, indexed) for p in paths]
            all_hits = [sum(a[0][i] for a in joint) for i in range(len(METHODS))]
            all_hit_events = [sum(a[0][i]>0 for a in joint) for i in range(len(METHODS))]
            all_work = [sum(a[1][i] for a in joint) for i in range(len(METHODS))]
            result.append([rev, len(paths), paths[chosen], joint[chosen][0], joint[chosen][1],
                           all_hits, all_hit_events, all_work])
        encoded = unique_ids(paths, ids)
        for i in encoded:
            previous[i].append(t)
            freq[i] += 1
            degree[i] += len(encoded)-1
        indexed.append((rev, encoded))
        # The next query should see its previous 32 updates.
        if t >= 32:
            old = indexed[t-32][1]
            for i in old:
                freq[i] -= 1
                degree[i] -= len(old)-1
    return result

def summary(events):
    n = len(events)
    out = {}
    for i, name in enumerate(METHODS):
        out[name] = {
            "one_anchor": {"hit_count":sum(e[3][i]>0 for e in events),
                "hit_rate":mean((e[3][i]>0) for e in events),
                "recall":mean(e[3][i]/(e[1]-1) for e in events),
                "incident_events":mean(e[4][i] for e in events)},
            "all_anchors": {"hit_rate":mean(e[6][i]/e[1] for e in events),
                "recall":mean(e[5][i]/(e[1]*(e[1]-1)) for e in events),
                "incident_events":mean(e[7][i]/e[1] for e in events)}}
    return {"n":n, "anchor_queries":sum(e[1] for e in events), "methods":out}

def main(verify):
    data = read_json(HERE/"commits.json.gz")
    events = {p:replay(s["revisions"]) for p,s in data.items()}
    write_json(HERE/"events.json.gz", {"methods":METHODS, "fields":["commit","m","anchor","hits","incident_events",
               "sum_hits_all_anchors","num_any_hit_all_anchors","incident_events_all_anchors"],"projects":events}, verify)
    pooled = summary([e for rows in events.values() for e in rows])
    groups = {p:summary(rows) for p,rows in events.items()}
    comparisons = {}
    rng = random.Random(7015)
    draws = [[rng.randrange(len(groups)) for _ in groups] for _ in range(20000)]
    for a,b in (("local32","frequency"),("local32","accumulated"),("last8anchor","accumulated"),
                ("last8anchor","sample8anchor")):
        for task in ("one_anchor","all_anchors"):
            ds = [v["methods"][a][task]["recall"]-v["methods"][b][task]["recall"] for v in groups.values()]
            boot = sorted(mean(ds[i] for i in draw) for draw in draws)
            comparisons[a+"-"+b+"-"+task] = {"equal_project_mean_difference":mean(ds),
                         "project_differences":dict(zip(groups.keys(), ds, strict=True)),
                         "exploratory_project_bootstrap_95":[boot[499], boot[19499]]}
    write_json(HERE/"results.json", {"projects":groups, "pooled":pooled, "comparisons":comparisons,
               "bootstrap_seed":7015}, verify)
    print(pooled)
    for name,item in comparisons.items():
        print(name, round(item["equal_project_mean_difference"]*100, 3), item["exploratory_project_bootstrap_95"])

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    main(ap.parse_args().verify)
