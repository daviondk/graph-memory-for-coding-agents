"""Build disjoint train-domain labels in a separate process. Does not touch adapted labels."""
from collections import defaultdict
from project import OUT,PRIV,PRE,save,get
if __name__=="__main__":
    mapping={r["task"]:r for r in get(PRIV/"controlled-evaluation-key.json.gz")}
    folds=defaultdict(dict)
    for case in get(PRE/"controlled-per-case.json.gz"):
        k=mapping[case["task"]];inv={v:u for u,v in k["node"].items()}
        folds[k["domain"]][k["id"]]=sorted(inv[v] for v in case["gold_claims"])
    for d,labels in folds.items():save(PRIV/("train-labels-"+d+".json.gz"),labels)

