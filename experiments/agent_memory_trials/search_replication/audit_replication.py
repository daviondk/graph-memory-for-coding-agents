"""Audit actual model logs against primary inputs; derive costs with no new calls."""
import csv
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

import replicate

ROOT = Path(__file__).resolve().parent
PRIMARY = ROOT.parent / "search"
FIELDS = ["input_tokens","cached_input_tokens","cache_write_input_tokens","output_tokens","reasoning_output_tokens"]


def load(path):
    return json.loads(path.read_bytes())


def audit():
    replicate.check()
    rows = list(csv.DictReader((ROOT/"observations.csv").open(encoding="utf-8",newline="")))
    allocation = load(ROOT/"allocation.json")
    costs = {a:Counter() for a in ("summary","raw","structured","all")}
    statuses = Counter()
    starts,ends = [],[]
    pairs = Counter((r["case"],r["arm"]) for r in rows)
    assert len(pairs)==len(rows)==len(allocation)==36 and set(pairs.values())=={1}
    traces = {r["id"]:r for r in load(ROOT/"executed_actions.json")}
    for row in rows:
        cell = next(c for c in allocation if c["id"]==row["id"])
        assert cell["case"]==row["case"] and cell["arm"]==row["arm"]
        path = Path("runs") / (row["id"]+".json")
        original, repeat = load(PRIMARY/path),load(ROOT/path)
        assert original["prompt"]==repeat["prompt"]
        assert original["prompt_sha256"]==repeat["prompt_sha256"]==hashlib.sha256(repeat["prompt"].encode()).hexdigest()
        assert repeat["model"]==replicate.MODEL and repeat["reasoning_effort"]=="low"
        assert repeat["command"][repeat["command"].index("-m")+1]==replicate.MODEL
        assert original["model"] != repeat["model"]
        ra, rb = original["attempts"],repeat["attempts"]
        assert {e["thread_id"] for a in ra for e in a["events"] if e["type"]=="thread.started"}.isdisjoint(
               {e["thread_id"] for a in rb for e in a["events"] if e["type"]=="thread.started"})
        statuses[repeat["status"]] += 1
        if row["pass"]!="":
            expected=f"{row['target']}:{row['target_line']}:"
            hits=[s.replace(chr(92),"/").removeprefix("./").startswith(expected) for s in traces[row["id"]]["stdout"]]
            assert int(any(hits))==int(row["pass"])
        for a in rb:
            starts.append(dt.datetime.fromisoformat(a["started_utc"]))
            ends.append(dt.datetime.fromisoformat(a["ended_utc"]))
            for dest in (costs[row["arm"]],costs["all"]):
                dest["attempts"]+=1
                dest["sum_model_seconds"]+=a["elapsed_s"]
                for f in FIELDS:
                    dest[f]+=(a.get("usage") or {}).get(f,0)
    distinct_threads={e["thread_id"] for r in rows for a in load(ROOT/"runs"/(r["id"]+".json"))["attempts"]
                      for e in a["events"] if e["type"]=="thread.started"}
    result=load(ROOT/"results.json")
    compare={}
    for title,p in [("primary",PRIMARY),("replication",ROOT)]:
        result=load(p/"results.json")
        compare[title]={a:{"pass":v["pass_count"],"unresolved":v["unresolved_choice_count"],
                           "unique_pass":v["unique_pass"],"ambiguous_pass":v["ambiguous_pass"]}
                        for a,v in result["arms"].items()}
    probe=load(ROOT/"transport_probe.json")
    output=dict(identical_prompt_pairs=len(rows),distinct_replicate_thread_ids=len(distinct_threads),
                statuses=dict(statuses),costs=costs,neutral_probe={"seconds":probe["elapsed_s"],"usage":probe["usage"]},
                elapsed_experiment_s=(max(ends)-min(starts)).total_seconds(),
                started_utc=min(starts).isoformat(),ended_utc=max(ends).isoformat(),
                paired_study_counts=compare)
    (ROOT/"replication_audit.json").write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(output,indent=2))


if __name__=="__main__":
    audit()
