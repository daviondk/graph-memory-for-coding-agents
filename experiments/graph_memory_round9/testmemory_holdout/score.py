"""Unseal each policy and compare with observed outcomes from full pytest on both versions."""
import collections
import json
import random
import statistics
from collect import ROOT,AGENT,RUNS,read,save,digest
from predict import unpack,status


def interval(rows,arm,other):
    blocks=collections.defaultdict(list)
    for r in rows:blocks[r["task"]].append(r)
    vals=[(sum(r["selected"][arm]-r["selected"][other] for r in g),len(g)) for g in blocks.values()]
    rng=random.Random(92103)
    boot=[]
    for _ in range(10000):
        a,b=map(sum,zip(*rng.choices(vals,k=len(vals))))
        boot.append(a/b)
    boot.sort()
    return [boot[249],boot[9749]]


def main():
    for f,h in read(ROOT/"prediction-lock.json").items():
        assert digest((ROOT/f).read_bytes())==h
    rows=unpack(ROOT/"forecasts.json.gz")
    bytask=collections.defaultdict(list)
    for r in rows:bytask[r["task"],r["direction"]].append(r)
    stats={};issues=[];final=[];verification=[];db=[]
    for (task,direction),cases in bytask.items():
        old,new=("base","gold") if direction=="fix" else ("gold","base")
        folder=RUNS/task
        hist=read(AGENT/"tasks"/task/"grades_v2"/"control.json")
        prior=unpack(folder/(old+".json.gz"));future=unpack(folder/(new+".json.gz"))
        build=read(folder/("testmon-"+old+"_build.json"));selected=read(folder/("testmon-"+new+"_select.json"))
        db.append(dict(task=task,direction=direction,build=build["db_bytes"],update=selected["db_bytes"],
              build_wall=build["wall_s"],update_wall=selected["wall_s"],old_pytest_wall=prior["wall"],new_pytest_wall=future["wall"]))
        assert set(build["reports"])=={r["node"] for r in cases},(task,direction,"testmon initial inventory")
        assert set(selected["reports"])<=set(build["reports"]) and selected["code"] in (0,1,5)
        for r in cases:
            node=r["node"]; expected=[]
            for side in (old,new):
                sn=hist[side]["tests"]
                x=[key for key in ("passed","failed","skip","errors") if any(node in a[key] for a in sn.values())]
                expected.append(x[0] if len(x)==1 else "unresolved")
            a=status(prior["reports"].get(node,[]));b=status(future["reports"].get(node,[]))
            valid=(a in ("passed","failed") and b in ("passed","failed") and [a,b]==expected)
            observed=status(selected["reports"].get(node,[])) if node in selected["reports"] else None
            ok=status(build["reports"][node])==a and (observed is None or observed==b)
            verification.append(dict(task=task,direction=direction,node=node,prior=a,current=b,historical=expected,
                                plugin_observed=observed,plugin_parity=ok,eligible=valid and ok))
            if not(valid and ok):
                issues.append(verification[-1])
                continue
            assert r["prior"]==a
            r["selected"]["testmon"]=node in selected["reports"]
            r.update(actual=b,changed=a!=b,new_failure=a=="passed" and b=="failed",
                seconds=sum(s for _,_,s in future["reports"][node]))
            final.append(r)
    for direction in ("fix","revert"):
        group=[r for r in final if r["direction"]==direction]
        conditions=list(group[0]["selected"])
        details={}
        for policy in conditions:
            selected=[r for r in group if r["selected"][policy]]
            stale=[r for r in group if r["changed"] and not r["selected"][policy]]
            details[policy]=dict(rerun=len(selected),stale=len(stale),missed_new_failures=sum(r["new_failure"] for r in stale),
                    successful_reuse=sum(not r["changed"] and not r["selected"][policy] for r in group),
                    estimated_test_phase_s=sum(r["seconds"] for r in selected))
        stats[direction]=dict(n=len(group),tasks=len({r["task"] for r in group}),flips=sum(r["changed"] for r in group),policies=details,
                symbol_minus_file_ci=interval(group,"symbol","file"),symbol_minus_testmon_ci=interval(group,"symbol","testmon"))
    storage=read(ROOT/"storage.json")
    stats["accounting"]=dict(eligible=len(final),scheduled=len(rows),excluded=len(issues),exclude_log=issues,
        per_direction_records=len(storage),median_shared_symbols=statistics.median(r["shared_keys"] for r in storage),
        med_compressed_exact_graph=statistics.median(r["observed_factored_gzip"] for r in storage),
        med_shared_only_gzip=statistics.median(r["shared_only_gzip"] for r in storage),
        median_plugin_db=statistics.median(sum(r["build"].values()) for r in db))
    save(ROOT/"outcomes.json",final);save(ROOT/"db-costs.json",db);save(ROOT/"verification.json",verification);save(ROOT/"results.json",stats)
    print(json.dumps({k:({kk:v for kk,v in z.items() if kk=="n"}|{c:[s["rerun"],s["stale"]] for c,s in z["policies"].items()}) for k,z in stats.items() if k!="accounting"},indent=2))
if __name__=="__main__":main()
