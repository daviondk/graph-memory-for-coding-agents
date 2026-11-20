"""Join sealed forecasts to observed returned rows and summarize without tuning."""
from collections import Counter, defaultdict
import gzip
import json
import random
import statistics
from extract import ROOT, digest, pack, rows, write_json
from replay import NAMES, MODES


def ci(rs, field, indices):
    groups = defaultdict(list)
    a, b = indices
    for r in rs:
        groups[r["id"]].append(r[field][a] - r[field][b])
    if len(groups) < 2:
        return None
    pairs = [(sum(v), len(v)) for v in groups.values()]
    rng = random.Random(790108)
    boot = []
    for _ in range(5000):
        draw = rng.choices(pairs, k=len(pairs))
        boot.append(100 * sum(x for x, y in draw) / sum(y for x, y in draw))
    boot.sort()
    return [round(boot[124], 3), round(boot[4874], 3)]


def summ(sample, tasks, raw):
    n = len(sample)
    ht = {k: [sum(r[k][i] for r in sample) for i in range(len(NAMES))] for k in ["hit", "page"]}
    gains = [r["hit"][3] - r["hit"][2] for r in sample]
    active = [r for r in sample if r["anchor_count"]]
    bounded = [r for r in sample if r["sizes"]]
    cost = [sum(r["sizes"][i] for r in bounded) for i in range(len(MODES))]
    return dict(n=n, raw_reads=raw, tasks=len({r["id"] for r in sample}), episodes=len(tasks),
                repos=len({r["repo"] for r in sample}), hit=dict(zip(NAMES, ht["hit"])), page=dict(zip(NAMES, ht["page"])),
                hit_le64={nm:sum(r["hit"][i] for r in sample if r["observed_rows"]<=64) for i,nm in enumerate(NAMES)},
                n_le64=sum(r["observed_rows"]<=64 for r in sample), active=len(active), multi=sum(r["anchor_count"]>1 for r in sample),
                active_any_hit=sum(r["ceiling"] for r in active), active_first_hit=sum(r["hit"][2] for r in active),
                eligible_any_or_fallback=sum(r["ceiling"] if r["anchor_count"] else r["hit"][2] for r in sample),
                near_vs_first=dict(wins=gains.count(1), losses=gains.count(-1), delta_pp=round(sum(gains)*100/n,3) if n else None,
                                   ci95_task_pp=ci(sample,"hit",(3,2))),
                first_vs_cursor_ci95_task_pp=ci(sample,"hit",(2,1)),
                ranges=len(bounded), range_tasks=len({r["id"] for r in bounded}), range_kind=dict(Counter(r["kind"] for r in bounded)),
                bytes=dict(zip(MODES,cost)), saved_extra=sum(r["sizes"][4]<r["sizes"][3] for r in bounded),
                incremental_bytes=cost[3]-cost[4], max_gain_per_request=max([r["sizes"][3]-r["sizes"][4] for r in bounded],default=0),
                display_bytes=sum(r["display_bytes"] for r in tasks), display_changes=sum(r["display_changes"] for r in tasks),
                mean_state=round(statistics.mean(r["state_bytes"] for r in sample),1) if n else None,
                peak=max([r["peak"] for r in tasks],default=0))


def main():
    lock = json.loads((ROOT/"lock.json").read_bytes())
    assert all(digest(ROOT/f)==v for f,v in lock["files"].items())
    truth = {r["id"]:r for r in rows(ROOT/"observations.gz")}
    total = Counter(r["panel"] for r in truth.values() for e in r["events"] if e and e[0] in ("view","shell"))
    scores, inventories = defaultdict(list), defaultdict(list)
    with gzip.GzipFile(str(ROOT/"scores.gz"),"wb",mtime=0) as out:
        for f in rows(ROOT/"forecasts.gz"):
            ident=f["panel"],f["cap"]
            if f["t"]==-1:
                inventories[ident].append(f)
                continue
            e=truth[f["id"]]["events"][f["t"]]
            shown=set(e[2])
            rec={key:value for key,value in f.items() if key not in ("pointers","anchors")}
            rec.update(kind=e[0], observed_rows=len(shown), anchor_count=len(f["anchors"]),
                       hit=[int(n in shown) for n in f["pointers"]],
                       page=[int(n is not None and (n-1)//16==(min(shown)-1)//16) for n in f["pointers"]],
                       ceiling=int(bool(shown.intersection(f["anchors"]))))
            out.write(pack(rec)+b"\n")
            scores[ident].append(rec)
    summary={f"{panel}/{cap}":summ(s,inventories[panel,cap],total[panel]) for (panel,cap),s in scores.items()}
    write_json("results.json",summary)
    write_json("results_lock.json", {"files":{s:digest(ROOT/s) for s in ["score.py","lock.json","scores.gz","results.json"]}})
    for k,s in summary.items():
        print(k, s["n"], s["hit"], s["near_vs_first"], s["ranges"], s["bytes"], "post", s["display_bytes"])


if __name__=="__main__":
    main()
