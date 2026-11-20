"""Verify content-addressed requests, membership-matched placebo and independent execution receipts."""
import json
from collections import Counter
from experiment import ROOT, read, check, digest, solver, save

def main():
    for lock in ("input-lock.json","sealed.json","oracle-sealed.json"):
        check(lock)
    logs = {p.name.split(".")[0]: read(p) for p in (ROOT/"calls").glob("*.json.gz")}
    h = solver()
    answers = read(ROOT/"answers.json") + read(ROOT/"oracle-answers.json")
    assert {a["call"] for a in answers} == set(logs)
    assert all(digest(h.canonical(x["request"])) == k for k,x in logs.items())
    for answer in answers:
        parsed=h.obj(logs[answer["call"]]["response"]["choices"][0]["message"]["content"])
        assert parsed["test"]-1==answer["index"]
    inputs=read(ROOT/"inputs.json")
    assert all(Counter(r["flags"]["graph"])==Counter(r["flags"]["shuffled"]) for r in inputs)
    reruns=read(ROOT/"executed.json")
    assert all(digest((ROOT/"tests"/x["log"]).read_bytes())==x["sha256"] for x in reruns)
    table={}
    rows=read(ROOT/"rows.json")
    for d in ("fix","revert"):
        for cohort in sorted({x["cohort"] for x in inputs}):
            group=[x for x in rows if x["direction"]==d and x["cohort"]==cohort]
            by={m:{x["task"]:x for x in group if x["arm"]==m} for m in set(x["arm"] for x in group)}
            table[d+"|"+cohort]={
                "tasks":len(by["off"]),
                "found":{m:sum(v["found_change"] for v in a.values()) for m,a in by.items()},
                "different_choice_graph_off":sum(v["node"]!=by["off"][k]["node"] for k,v in by["graph"].items()),
                "ceiling":sum(v["total_changes"]>0 for v in by["off"].values())}
    counts=Counter()
    for x in logs.values():counts.update({k:x["response"]["usage"][k] for k in ("prompt_tokens","completion_tokens","total_tokens")})
    save(ROOT/"audit.json",dict(logical=len(answers),physical=len(logs),requests_verified=len(logs),
         matched_placebos=len(inputs),isolated_verified=len(reruns),physical_usage=counts,
         seconds=sum(t["elapsed"] for x in logs.values() for t in x["attempts"]),panels=table))
if __name__=="__main__":
    main()
