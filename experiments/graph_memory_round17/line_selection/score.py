"""Score the frozen rankings with the published SWE-Explore evaluator."""
import collections
import random
import sys
from pathlib import Path
from statistics import mean

from predict import ROOT, WORK, digest, load, write

NATIVE = Path("D:/CodexResearch/x20-round15-external-scoring")
REFERENCE = WORK / "graph_memory_round15/external_scoring"
sys.path.insert(0, str(NATIVE))
from swe_eval import ExploreEvaluator


def contrast(rows, candidate, baseline):
    groups = collections.defaultdict(list)
    different = improved = worse = 0
    for row in rows:
        diff = row["scores"][candidate]["precision"] - row["scores"][baseline]["precision"]
        groups[row["instance_id"]].append(diff)
        different += row["regions"][candidate] != row["regions"][baseline]
        improved += diff > 1e-12
        worse += diff < -1e-12
    values = [mean(group) for group in groups.values()]
    rng = random.Random(1731)
    distribution = sorted(sum(rng.choices(values,k=len(values))) / len(values) for _ in range(5000))
    return dict(delta=mean(values), ci=[distribution[124], distribution[4874]], different=different,
                win_episodes=improved, loss_episodes=worse, unique_tasks=len(values))


def main():
    locked = load(ROOT/"prediction-lock.json")["files"]
    for name, expected in locked.items():
        assert digest(ROOT/name) == expected, name
    benchmark_path = NATIVE/"swe-explore.jsonl"
    assert digest(benchmark_path) == load(REFERENCE/"coverage.json")["panels"]["SWE-Explore"]["sha"]
    assert digest(NATIVE/"swe_eval.py") == load(REFERENCE/"native-source.json")["swe_eval.py"]["sha256"]
    evaluator = ExploreEvaluator(benchmark_path)
    predictions = load(ROOT/"predictions.json.gz")
    panels = collections.defaultdict(list)
    missing = []
    for row in predictions:
        iid = row["instance_id"]
        if iid not in evaluator.bench_data_dict:
            missing.append(iid)
            continue
        core = evaluator.bench_data_dict[iid]["ground_truth"]["read_core_regions"]
        assert all(r["start"] >= 1 and r["end"] >= r["start"] for r in core), iid
        scores = {arm: evaluator.evaluate(lambda q, i: regions, [iid], ["precision","recall","f1_score"])[iid]
                  for arm,regions in row["pred"].items()}
        item = dict(instance_id=iid, panel=row["panel"], source=row["source"], scores=scores, regions=row["pred"],
                    lines_seen=row["lines_seen"], scope_matching_blocks=row["scope_matching_blocks"])
        panels[row["panel"]].append(item)
    arms = list(predictions[0]["pred"])
    cohorts = dict(panels)
    for source in sorted({r["source"] for r in panels["independent"]}):
        cohorts[source] = [r for r in panels["independent"] if r["source"] == source]
    reports = {}
    for key, rows in cohorts.items():
        valid = [r for r in rows if r["lines_seen"]]
        reports[key] = dict(n=len(rows), tasks=len({r["instance_id"] for r in rows}),
            nonempty=len(valid), over_budget=sum(r["lines_seen"]>60 for r in rows),
            with_link=sum(bool(r["scope_matching_blocks"]) for r in rows),
            means={arm:{met:mean(r["scores"][arm][met] for r in rows) for met in ("precision","recall","f1_score")}
                   for arm in arms},
            precision_nonempty={arm:mean(r["scores"][arm]["precision"] for r in valid) if valid else None for arm in arms},
            contrasts={f"{a}-{b}":contrast(rows,a,b) for a,b in [
                ("scope24","lexical24"),("scope24","first"),("lexical24","first"),
                ("scope0","lexical0"),("lexical24","lexical0")]})
    write("scored.json.gz", [r for v in panels.values() for r in v])
    write("results.json", dict(panels=reports, unmatched=sorted(missing), test_data=digest(benchmark_path),
                                native_scorer=digest(NATIVE/"swe_eval.py")))
    for k, r in reports.items():
        print(k,r["n"],r["nonempty"],r["with_link"],{a:round(m["precision"],4) for a,m in r["means"].items()},
              r["contrasts"]["scope24-lexical24"])


if __name__ == "__main__":
    main()

