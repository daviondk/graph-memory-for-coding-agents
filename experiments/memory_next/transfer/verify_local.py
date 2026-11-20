"""Offline, stdlib only. Independently recompute pool membership, per-item scores, and clocks."""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def obj(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def rows(name):
    with (ROOT / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def digest(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()

def flag(s):
    assert s in {"True","False"}, s
    return s == "True"

def check_locks():
    for name, h in obj("blind_freeze.json")["sha256"].items():
        assert digest(name) == h, name
    assert obj("results.json")["blind_freeze_sha256"] == digest("blind_freeze.json")
    for name, h in obj("lite_times_receipt.json").items():
        assert digest(name) == h, name
    if (ROOT/"MANIFEST.sha256").exists():
        for line in (ROOT/"MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
            h, name = line.split("  ", 1)
            assert digest(name) == h, name

def check_chronology(sources):
    tasks = rows("full_chronology.csv")
    assert len({r["target"] for r in tasks}) == len(tasks) == 357
    for q in tasks:
        assert q["complete_cutoff"] == "1"
        status = []
        for did in q["refs"].split("|"):
            d = sources.get(did)
            if d is None: v="absent"
            elif d["repo"].lower()==q["repo"].lower() and d["pr"]==q["target_pr"]: v="same_target_pr"
            elif not d["merged"]: v="uncertain"
            elif d["merged"] >= q["cutoff"]: v="after_or_at"
            else: v="past"
            status.append(v)
        assert status == q["link_states"].split("|")
        expected = "past" if "past" in status else "unknown" if "uncertain" in status else "not_past_or_absent"
        assert q["any_past_gold"] == expected
        assert int(q["any_same_target_pr"]) == ("same_target_pr" in status)
    summaries = obj("full_availability.json")
    for scope, subset in [("all", tasks), ("lite",[q for q in tasks if q["lite"]=="1"]), ("other",[q for q in tasks if q["lite"]=="0"])]:
        assert Counter(q["any_past_gold"] for q in subset) == summaries[scope]["chronology"]
        assert sum(int(q["any_same_target_pr"]) for q in subset) == summaries[scope]["same_pr"]
    return {q["target"]:q for q in tasks}

def check_ranks(sources, tasks):
    scored={(r["id"],r["scope"]):r for r in rows("per_question.csv")}
    assert len(scored)==3*258
    totals=defaultdict(lambda: [0, 0, 0.])
    seen = set()
    with gzip.open(ROOT/"blind_ranks.jsonl.gz","rt",encoding="utf-8") as f:
        for line in f:
            r=json.loads(line)
            key=(r["target"],r["scope"])
            q=tasks[r["target"]]
            assert key not in seen and q["lite"]=="0"
            seen.add(key)
            assert r["cutoff"]==q["cutoff"]
            expected = {i for i,d in sources.items() if i!=q["target"] and
                        (r["scope"]=="all_time" or d["repo"].lower()==q["repo"].lower()) and
                        (r["scope"]=="repo_release" or d["merged"] and d["merged"]<q["cutoff"])}
            n=r["candidates"]; assert n==len(expected)==int(scored[key]["n"])
            gold=scored[key]["gold"].split("|")
            assert set(gold)==set(q["refs"].split("|"))
            assert flag(scored[key]["available"])==bool(expected.intersection(gold))
            assert len(r["ranks"])==7
            for arm,rank in r["ranks"].items():
                assert len(rank)==n and set(rank)==expected
                ix=next((j for j,d in enumerate(rank,1) if d in gold),0)
                h1=ix==1; h5=1<=ix<=5; rr=1/ix if ix else 0
                t=totals[(r["scope"],arm)]
                t[0]+=h1; t[1]+=h5; t[2]+=rr
                assert flag(scored[key][arm+"_1"])==h1 and flag(scored[key][arm+"_5"])==h5
                assert math.isclose(float(scored[key][arm+"_rr"]),rr)
                assert flag(scored[key][arm+"_first"])==bool(rank and rank[0]==gold[0])
                assert flag(scored[key][arm+"_last"])==bool(rank and rank[0]==gold[-1])
    assert seen==set(scored)
    published=obj("results.json")["results"]
    for (scope,arm),(h1,h5,total_rr) in totals.items():
        a=published[scope]["all"]["arms"][arm]
        assert a["hits1"]==h1 and a["hits5"]==h5 and math.isclose(a["mrr"],total_rr/258)

def check_lite(sources):
    records=rows("lite_chronology.csv")
    table={r["ordinal"]:r for r in rows("query_times_lite.csv")}
    members={r["instance_id"] for r in rows("source_times_lite.csv")}
    assert len(records)==len(table)==99 and len(members)==300
    verdicts=defaultdict(Counter)
    for r in records:
        q=table[r["ordinal"]]; assert q["target"]==r["target"] and q["opening_complete"]=="1"
        gold=r["gold"].split("|"); pick=r["qwen"]; assert pick in members
        for clock, field in [("issue_start","cutoff_utc"),("pr_open","pr_open"),("pr_merge","pr_merge")]:
            cutoff=q[field]
            def state(i):
                if i not in members:return "absent"
                d=sources[i]
                if d["repo"].lower()==q["repo"].lower() and d["pr"]==q["target_pr"]:return "nonpast"
                if not d["merged"] or not cutoff:return "unknown"
                return "past" if d["merged"]<cutoff else "nonpast"
            for rule,g in [("any",gold),("first",gold[:1]),("last",gold[-1:])]:
                choices={state(i) for i in g}
                available="past" if "past" in choices else "unknown" if "unknown" in choices else "nonpast_or_absent"
                assert r[clock+"_"+rule+"_gold_available"]==available
                assert flag(r["qwen_"+rule+"_correct"])==(pick in g)
                if pick in g:verdicts[(clock,rule)][state(pick)]+=1
    published=obj("lite_chronology.json")["clocks"]
    for (clock,rule),counts in verdicts.items():
        assert counts==published[clock][rule+"_qwen_hits"]
    checks=rows("lite_patch_overlap.csv")
    for name, subset in [("gold_same_pr",[r for r in checks if flag(r["same_pr"])]),
                         ("gold_other_pr",[r for r in checks if not flag(r["same_pr"])])]:
        d=obj("lite_patch_overlap.json")[name]
        assert len(subset)==d["link_pairs"]
        assert sum(flag(r["changed_lines_exact"]) for r in subset)==d["changed_lines_exact"]
        assert math.isclose(sum(float(r["lines_jaccard"]) for r in subset)/len(subset),d["mean_line_jaccard"])

def main():
    check_locks()
    sources={r["id"]:r for r in rows("history_times_full.csv")}
    assert len(sources)==1007 and sum(bool(d["merged"]) for d in sources.values())==1004
    tasks=check_chronology(sources)
    check_ranks(sources,tasks)
    check_lite(sources)
    print("OK: frozen hashes, 1,007 sources, 357 timelines, 5,418 full ranking lists, 99 Lite choices and 102 patch pairs")

if __name__=="__main__":
    main()

