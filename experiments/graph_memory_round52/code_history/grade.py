"""Open sealed forecasts, independently recover delayed next-view labels, report paired metrics."""
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
import json
import numpy as np
from prepare_data import HERE, read, save, sha

METHODS = ["mru", "lfu", "incoming", "outgoing", "baseline", "sham", "graph"]

def group_mean(rows, key, col):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row["hit"][col])
    return {g: float(np.mean(a)) for g, a in sorted(groups.items())}

def metrics(rows):
    if not rows:
        return {"n":0}
    return {"n":len(rows), "issues":len({r["issue"] for r in rows}), "repos":len({r["repo"] for r in rows}),
            "hits":{p:sum(r["hit"][p] for r in rows) for p in METHODS},
            "micro":{p:float(np.mean([r["hit"][p] for r in rows])) for p in METHODS},
            "issue_macro":{p:float(np.mean(list(group_mean(rows,"issue",p).values()))) for p in METHODS}}

def signflip(arr):
    arr = arr[np.abs(arr) > 1e-14]
    n = len(arr)
    observed = abs(arr.sum())
    if not n:
        return 1.
    if n <= 20:
        sums = np.zeros(1)
        for x in arr:
            sums = np.concatenate([sums + x, sums - x])
        return float((np.abs(sums) >= observed - 1e-12).mean())
    rng = np.random.default_rng(520812)
    count = 0
    for _ in range(100):
        signs = rng.choice([-1.,1.], size=(1000, n))
        count += np.count_nonzero(np.abs(signs @ arr) >= observed - 1e-12)
    return float((count + 1) / 100001)

def paired(rows, left="graph", right="baseline", key="issue"):
    l, r = group_mean(rows,key,left), group_mean(rows,key,right)
    assert l.keys() == r.keys()
    a = np.array([l[k] - r[k] for k in l])
    rng = np.random.default_rng(520812)
    means = rng.choice(a, size=(10000,len(a)), replace=True).mean(axis=1)
    return {"unit":key, "units":len(a), "gain_units":int((a>0).sum()), "loss_units":int((a<0).sum()),
            "mean":float(a.mean()), "ci95":np.quantile(means,[.025,.975]).tolist(),
            "sign_flip_p":signflip(a), "choice_changes":sum(s["pred"][left] != s["pred"][right] for s in rows),
            "episode_wins":sum(s["hit"][left] > s["hit"][right] for s in rows),
            "episode_losses":sum(s["hit"][left] < s["hit"][right] for s in rows)}

def main():
    seal = read(HERE / "forecast_seal.json")
    for name, digest in seal.items():
        assert sha(HERE / name) == digest
    predictions = read(HERE / "forecasts.json.gz")
    traces = {t["issue"]: t for t in read(HERE / "test_trace.json.gz")}
    repos_train = set(read(HERE / "model.json")["all_train_repos"])
    rows = []
    for pred in predictions:
        t = traces[pred["issue"]]
        at, path = pred["at"], pred["path"]
        pos, = [i for i,(tick,typ,p) in enumerate(t["events"]) if tick==at and typ=="E" and p==path]
        prefix, future = t["events"][:pos+1], t["events"][pos+1:]
        pool = []
        for _,typ,p in reversed(prefix):
            if typ in ("R","E") and p!=path and p not in pool:
                pool.append(p)
        assert pool == pred["pool"] and pred["pred"]["mru"] == next(iter(pool),None)
        seen = Counter(p for _,typ,p in prefix if typ in ("R","E"))
        assert pred["pred"]["lfu"] == max(pool, key=lambda p:seen[p], default=None)
        # Independent conditional controls via prefix subsequences.
        switches = [(l,r) for l,r in zip([p for _,k,p in prefix if k!="B"],
                                          [p for _,k,p in prefix if k!="B"][1:]) if l!=r]
        mru = pred["pred"]["mru"]
        assert pred["pred"]["incoming"] == next((l for l,r in reversed(switches) if r==path),mru)
        assert pred["pred"]["outgoing"] == next((r for l,r in reversed(switches) if l==path),mru)
        assert len(set(switches)) == pred["switch_edges"]
        target, target_at, barrier, end = None, None, False, "end"
        for tick,typ,p in future:
            if typ == "E":
                end = "next_edit"
                break
            if typ == "B":
                barrier = True
            elif typ == "R":
                target, target_at, end = p, tick, "view"
                break
        status = ("censored" if target is None else "same" if target==path else
                  "reachable_other" if target in pool else "unseen_other")
        hit = {p:int(target == path or target == pred["pred"][p]) for p in METHODS} if target is not None else {}
        rows.append({**pred, "status":status, "end":end,"target":target,"target_at":target_at,"opaque_between":barrier,
                     "novel_repo":t["repo"] not in repos_train,"hit":hit})
    assert len({(r["issue"],r["at"]) for r in rows})==len(rows)
    valid = [r for r in rows if r["status"]!="censored"]
    categories = {"all":valid,"novel_repo":[r for r in valid if r["novel_repo"]],
                  "shared_repo":[r for r in valid if not r["novel_repo"]],
                  "other":[r for r in valid if r["status"]!="same"],
                  "reachable_other":[r for r in valid if r["status"]=="reachable_other"],
                  "reachable_two_options":[r for r in valid if r["status"]=="reachable_other" and len(r["pool"])>=2],
                  "strict":[r for r in valid if not r["opaque_between"]],
                  **{p:[r for r in valid if r["panel"]==p] for p in ("real_swe","real_swe_followup")}}
    keyed = defaultdict(list)
    for r in rows:
        keyed[r["issue"]].append(r)
    out = {"opportunities":dict(Counter(r["status"] for r in rows)),
           "censoring":dict(Counter(r["end"] for r in rows if r["status"]=="censored")),
           "issues_with_edits":len(keyed),"input_issues":len(traces),
           "by_group":{k:metrics(group) for k,group in categories.items()},
           "paired_primary":paired(valid),"paired_equal_repo":paired(valid,key="repo"),
           "paired_graph_vs_controls":{p:paired(valid,right=p) for p in METHODS if p!="graph"},
           "per_repo":{g:metrics([r for r in valid if r["repo"]==g]) for g in sorted({r["repo"] for r in valid})},
           "state":{"switch_keys_peak_by_issue_median_max":np.quantile([max(r["switch_edges"] for r in grp) for grp in keyed.values()],[.5,1]).tolist(),
                    "typed_keys_peak_by_issue_median_max":np.quantile([max(r["typed_edges"] for r in grp) for grp in keyed.values()],[.5,1]).tolist(),
                    "with_previous_edge":sum(r["supported"] for r in valid),
                    "with_two_options":sum(len(r["pool"])>=2 for r in valid)}}
    save("episodes.json.gz",rows)
    save("results.json",out)
    print(json.dumps({k:out[k] for k in ("opportunities","censoring","paired_primary","paired_equal_repo","state")}))
    for k,v in out["by_group"].items():
        print(k, v["n"],v.get("issues"),v.get("hits",{}))

if __name__ == "__main__":
    main()

