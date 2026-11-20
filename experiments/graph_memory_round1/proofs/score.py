"""Aggregate all paired outcomes, with equal weight per repository for primary inference."""
import collections, gzip, hashlib, json, random, statistics
from pathlib import Path
from run import ROOT, ARMS

def quantile(values, q):
    n=(len(values)-1)*q
    return values[int(n)]*(int(n)+1-n) + values[min(int(n)+1,len(values)-1)]*(n-int(n))

def main():
    manifest=json.loads((ROOT/"receipt.json").read_text(encoding="utf-8"))
    target={}
    for m in manifest["repositories"]:
        shard=ROOT/"shards"/(m["repo"]+".jsonl.gz")
        assert m["sha256"]==hashlib.sha256(shard.read_bytes()).hexdigest()
        rows=[json.loads(x) for x in gzip.decompress(shard.read_bytes()).splitlines() if x]
        assert len(rows)==m["rows"]==sum(x["sampled"] for x in m["windows"])
        assert all(x["group"]==m["group"] for x in rows)
        target[m["repo"]]=rows
    output={}
    for group in ["A","B","all"]:
        repos={k:v for k,v in target.items() if v and (v[0]["group"]==group or group=="all")}
        rows=sum(repos.values(),[])
        def avg(arm,metric,r):
            return sum(x[arm][metric] for x in r)/len(r)
        per={repo:{a:{m:avg(a,m,v) for m in ["fast","validated","reads","path_utf8","providers","edges"]} for a in ARMS}
             for repo,v in repos.items()}
        arms={a:{m:{"total":sum(r[a][m] for r in rows),"macro":statistics.mean(p[a][m] for p in per.values())}
                 for m in ["fast","validated","reads","path_utf8","providers","edges"]} for a in ARMS}
        differences={}
        for method,base in [("historical","short3"),("diverse","short3"),("short3","one"),("historical","diverse")]:
            repository_gains=[p[method]["fast"]-p[base]["fast"] for p in per.values()]
            rng=random.Random(261118)
            boot=sorted(statistics.mean(rng.choices(repository_gains,k=len(repository_gains))) for _ in range(10000))
            differences[method+"-"+base]={"macro":statistics.mean(repository_gains),
                "repo_ci":[quantile(boot,.025),quantile(boot,.975)],
                "paired_win":sum(r[method]["fast"]>r[base]["fast"] for r in rows),
                "paired_loss":sum(r[method]["fast"]<r[base]["fast"] for r in rows),
                "repo_deltas":dict(zip(repos,repository_gains))}
        output[group]={"repositories":len(per),"queries":len(rows),"gold_lost":sum(1-r["truth"] for r in rows),
            "at_least_two_paths":sum(r["alternatives"]>=2 for r in rows),
            "above_three_paths":sum(r["alternatives"]>3 for r in rows),
            "changed_selected_sets":sum(set(map(tuple,r["historical"]["proofs"]))!=set(map(tuple,r["short3"]["proofs"])) for r in rows),
            "arms":arms,"differences":differences,"per_repo":per}
    (ROOT/"results.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
    for g,s in output.items():
        print(g,s["queries"],s["gold_lost"],s["at_least_two_paths"],s["above_three_paths"],s["changed_selected_sets"],
              {a:[s["arms"][a][m]["total"] for m in ("fast","validated","reads","path_utf8")] for a in ARMS},
              {k:(round(v["macro"]*100,3),[round(x*100,3) for x in v["repo_ci"]],v["paired_win"],v["paired_loss"]) for k,v in s["differences"].items()})
if __name__=="__main__":
    main()

