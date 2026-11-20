"""Secondary robustness analysis of sealed outcomes, exact project sign flips and equal issue weights."""
from collections import defaultdict
import gzip
from itertools import product
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent

def read(name):
    with gzip.open(ROOT / name / "scored.jsonl.gz", "rt", encoding="utf8") as stream:
        return [json.loads(line) for line in stream]

def contrast(rows, new, old):
    projects = defaultdict(list)
    issues = defaultdict(list)
    for issue, project, _, _, _, arms in rows:
        difference = arms[new][0] - arms[old][0]
        projects[project].append(difference)
        issues[issue].append(difference)
    totals = np.asarray([sum(v) for v in projects.values()])
    total_effect = int(totals.sum())
    exact = [abs(int(totals @ signs)) >= abs(total_effect) for signs in product((-1, 1), repeat=len(totals))]
    without = {k:(total_effect - sum(v))/(len(rows)-len(v)) for k,v in projects.items()}
    return {"actions":len(rows), "issues":len(issues), "projects":len(projects),
            "hit_difference":total_effect, "per_action":total_effect/len(rows),
            "equal_issue":float(np.mean([np.mean(v) for v in issues.values()])),
            "equal_project":float(np.mean([np.mean(v) for v in projects.values()])),
            "nonzero_issues":sum(sum(v)!=0 for v in issues.values()), "nonzero_projects":int(np.count_nonzero(totals)),
            "p_two_sided_project_sign_flip":sum(exact)/len(exact), "omit_one_project":without}

def main():
    a=read("real_swe")
    b=read("real_swe_followup")
    assert {r[0] for r in a}.isdisjoint({r[0] for r in b})
    out={}
    for name, rows in (("A",a),("B",b),("A_and_B",a+b)):
        pairs=[("typed","point"),("typed","lru")]
        if name=="B":
            pairs.extend([("mixed","lru"),("mixed","typed")])
        out[name]={f"{new}-{old}":contrast(rows,new,old) for new,old in pairs}
    (ROOT/"swe_robustness.json").write_text(json.dumps(out,indent=2),encoding="utf8")
    for panel, methods in out.items():
        for name,row in methods.items():
            print(panel,name,row["hit_difference"],round(100*row["equal_issue"],2),
                  round(100*row["equal_project"],2),row["p_two_sided_project_sign_flip"])

if __name__=="__main__":
    main()
