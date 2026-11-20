"""Describe the fixed 4 KiB checkpoint predictions by true page crossings after outcomes were opened."""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "real_swe"))
from transfer import future, line_target, stream

ARMS = ("lru", "point", "typed")

def rows(path):
    with gzip.open(path, "rt", encoding="utf8") as file:
        for line in file:
            yield json.loads(line)

def analyze(name, sources, scores_file):
    historical = name == "SWE-smith"
    scores = {}
    for row in rows(scores_file):
        if historical:
            issue, time, length, all_scores = row
            scores[issue, time] = length, {a: all_scores[a + "@4096"] for a in ARMS}
        else:
            issue, _, time, length, _, metrics = row
            scores[issue, time] = length, metrics
    observations = []
    for path in sorted(sources.glob("source_*.jsonl.gz")):
        for task in rows(path):
            for time, pages, *_ in stream(task):
                edit = future(task["events"], time)
                if not edit or not edit[2]:
                    continue
                issue = task["instance"]
                length, metrics = scores.pop((issue, time))
                position = line_target(pages, edit[0], edit[1])
                width = 0
                if position:
                    target_path, start, end, _ = position
                    assert target_path == edit[0] and end - start + 1 == length
                    width = 1 + (end - 1) // 12 - (start - 1) // 12
                else:
                    assert length == 0
                observations.append((issue, time, width, {a: metrics[a][:3] for a in ARMS}))
    assert not scores
    groups = {"unlocated": [], "one_page": [], "multiple_pages": []}
    for rec in observations:
        groups["unlocated" if not rec[2] else "one_page" if rec[2] == 1 else "multiple_pages"].append(rec)
    summary = {}
    for label, group in groups.items():
        n = len(group)
        stat = {}
        for arm in ARMS:
            m = [r[-1][arm] for r in group]
            stat[arm] = {"full":sum(x[0] for x in m), "start":sum(x[2] for x in m)}
        differences = {}
        for control in ("lru", "point"):
            effects = Counter(r[-1]["typed"][0] - r[-1][control][0] for r in group)
            differences[control] = {"wins":effects[1], "losses":effects[-1], "ties":effects[0]}
        summary[label] = {"n":n, "arms":stat, "typed_vs":differences}
    return observations, summary

def main():
    dest = ROOT / "geometry_by_action.jsonl.gz"
    output = {}
    with gzip.open(dest, "wt", encoding="utf8") as log:
        for name, inputs, srcscore in [("SWE-smith","context/replication","serialized_writer/scored_steps.jsonl.gz"),
                                      ("SWE-bench Verified A","real_swe","real_swe/scored.jsonl.gz"),
                                      ("SWE-bench Verified B","real_swe_followup","real_swe_followup/scored.jsonl.gz")]:
            records, summary = analyze(name, ROOT / inputs, ROOT / srcscore)
            output[name] = summary
            for r in records:
                log.write(json.dumps([name, *r],separators=(",",":"))+"\n")
    (ROOT / "geometry_results.json").write_text(json.dumps(output,indent=2),encoding="utf8")
    for name, groups in output.items():
        for label, result in groups.items():
            print(name,label,result["n"],[result["arms"][a]["full"] for a in ARMS])

if __name__ == "__main__":
    main()
