"""Paired comparison of predeclared follow-up arms to the native baseline on the same test queries."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"holdout80"))
from heldout import differences
import study as s
def main(stage):
    ext=s.read(HERE/f"test-{stage}"/"outcomes.json.gz")
    main=s.read((s.HERE if stage=="dev" else s.HERE/"train_bm25")/"outcomes.json.gz")
    data=main+ext
    pairs=[("degrees","dense"),("degrees","typed"),("role_cost","degrees"),("full_typed_cost","role_cost_degrees"),
           ("role_degrees","dense"),("role_degrees","role"),("role_degrees","degrees"),("role_degrees","typed"),
           ("structural_only","dense"),("role_cost_degrees","dense"),("role","dense"),("role_cost","dense")]
    out={}
    for pol in ("prefix","skip"):
        rows=[r for r in data if r["policy"]==pol]
        for a,b in pairs:
            out[f"{a}-{b}/{pol}"]=differences(rows,a,b)
    s.put(HERE/f"contrasts-{stage}.json",out)
    print(stage,[(k,out[k]["full_support"]) for k in ("degrees-dense/prefix","role_degrees-dense/prefix","role_degrees-typed/prefix")],flush=True)
if __name__=="__main__":main(sys.argv[1])
