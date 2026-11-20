"""Independent descriptive audits and reference/control checks. No fitting or policy changes."""
import json
import math
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
def read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf8").splitlines()]

if __name__ == "__main__":
    rows = read_jsonl(ROOT/"potential_outcomes.jsonl")
    ds = {(r["dataset"],r["id"]):r for r in rows}
    scores = json.loads((ROOT/"results.json").read_bytes())
    topics = json.loads((ROOT/"sources/topics.json").read_bytes())
    public = {f"{t['number']}_{r['number']}":r for t in topics for r in t["turn"]}
    actions = defaultdict(list)
    folds = defaultdict(dict)
    for r in read_jsonl(ROOT/"decisions.jsonl"):
        evalname = r["evaluation"]
        bench = evalname.split("_")[-1] if "_to_" in evalname else evalname.split("_")[0]
        item = ds[(bench,r["id"])]
        assert item[r["action"]]["grades"] == r["chosen_grades"]
        assert folds[bench].setdefault(r["group"],r["fold"]) == r["fold"]
        actions[evalname].append((item,r))
    audit = {}
    for name, records in actions.items():
        n = len(records)
        report = scores[name]
        assert n == report["n"] ==len({r['id'] for item,r in records})
        assert sum(r["action"]=="on" for item,r in records)==report["reads"]
        for cut,metric in enumerate(["primary","secondary"]):
            mean = sum(r["chosen_grades"][cut] for item,r in records)/n
            assert math.isclose(mean,report[metric]["gate"],abs_tol=1e-12)
        first = [(item,r) for item,r in records if item['features'][2]==1.]
        k = sum(1 for item,r in first if r['action']=='off')
        trivial = [item["off" if item["features"][2] else "on"]["grades"][0] for item,r in records]
        audit[name] = dict(first_turns=len(first), skipped_first=k, trivial_skip_empty_mean=sum(trivial)/n,
                           trivial_reads=n-len(first), counts_by_fold=dict(Counter(r['fold'] for item,r in records)))
    match_counts = Counter()
    for (bench,sid),row in ds.items():
        if bench=="cast":
            t = public[sid]
            same = t['raw_utterance'].strip() == t['automatic_rewritten_utterance'].strip()
            changed_ranking = row['on']['rank'] != row['off']['rank']
            match_counts[f"identical_query_{int(same)}_changed_top5_{int(changed_ranking)}"] += 1
    audit["cast_query_invariance"]=dict(match_counts)
    print(json.dumps(audit,indent=2))
    (ROOT/"control_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf8")
