"""Score fixed out-of-project selections on observed branches. There is no solver invocation here."""
import json
from collections import Counter
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
ARMS = ["HISTORY", "NONE", "SIGNAL", "REFLECT", "BOTH"]


def get(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))


def main():
    rows, labels, pred = get("features.json"), get("labels.json"), get("predictions.json")
    assert set(pred) == set(labels) == {x["id"] for x in rows}
    projects = sorted({x["project"] for x in rows})
    proj = np.array([projects.index(x["project"]) for x in rows])
    sizes = np.bincount(proj)
    policies = list(pred[rows[0]["id"]]) + ARMS + ["hindsight"]
    vectors = {}
    choices = {}
    by_project = {}
    for key in policies:
        selected = []
        hits = []
        for row in rows:
            eid = row["id"]
            if key == "hindsight":
                hits.append(max(labels[eid].values()))
                continue
            arm = key if key in ARMS else pred[eid][key]
            selected.append(arm)
            hits.append(labels[eid][arm])
        choices[key] = Counter(selected)
        vec = vectors[key] = np.array(hits, dtype=int)
        by_project[key] = np.bincount(proj, weights=vec).astype(int).tolist()
    rng = np.random.default_rng(41433)
    picks = rng.integers(len(projects), size=(10000, len(projects)))
    denom = sizes[picks].sum(axis=1)
    results = {}
    for key, vec in vectors.items():
        by = np.array(by_project[key])
        results[key] = {"solved": int(vec.sum()), "n": len(rows), "automation_selected_formats": choices[key],
                        "rate": float(vec.mean()), "macro_rate": float((by/sizes).mean()),
                        "per_project_solved": dict(zip(projects, by.tolist()))}
    pairs = {}
    for key, alt in vectors.items():
        if key == "graph":
            continue
        mainvec = vectors["graph"]
        by = np.array(by_project["graph"]) - np.array(by_project[key])
        boot = by[picks].sum(axis=1)/denom
        d = mainvec-alt
        pairs["graph_minus_"+key] = {"delta": float(d.mean()), "ci95_project": np.quantile(boot, [.025, .975]).tolist(),
                              "wins": int((d>0).sum()), "losses": int((d<0).sum()), "ties": int((d==0).sum()),
                              "both_solved": int(((mainvec == 1)&(alt == 1)).sum()),
                              "both_failed": int(((mainvec == 0)&(alt == 0)).sum()),
                              "projects_gain": int((by>0).sum()), "projects_loss": int((by<0).sum()),
                              "projects_equal": int((by==0).sum())}
    out = {"denominator_by_project": dict(zip(projects,sizes.tolist())), "results":results, "paired":pairs,
           "episode_outcomes": {r["id"]: {p: int(v[i]) for p,v in vectors.items()} for i,r in enumerate(rows)}}
    (ROOT/"score.json").write_text(json.dumps(out,sort_keys=True, indent=2)+"\n",encoding="utf-8")
    print("success", {k: v["solved"] for k,v in results.items()})
    print("primary", pairs["graph_minus_constant_cv"])
    print("controls", {k:(round(v["delta"],3),v["wins"],v["losses"]) for k,v in pairs.items()})


if __name__ == "__main__":
    main()
