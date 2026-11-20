"""Read relevance only after frozen predictions. A seed is not an independent query sample."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
load=lambda path:json.loads(path.read_text(encoding="utf8"))


def evaluate(ranks,gold):
    values=[]
    for i,r in enumerate(gold):
        accepted=r["associated_library_indices"]
        denom=r["n_valid_relations"]
        v=np.isin(ranks[i],accepted)
        pos=np.flatnonzero(v)
        values.append([int(v[0]),int(v[:5].any()),1/(1+int(pos[0])) if pos.size else 0.,
                       float(v[:5].sum()/denom) if denom else 0.])
    return np.array(values)


def main(verify=False):
    locked=load(ROOT/"blind_lock.json")["files"]
    assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in locked.items())
    ranked=np.load(ROOT/"predictions.npz")["rankings"]
    gold=load(ROOT.parent/"scoring-inputs.json")
    sets={"lite":np.arange(99),"extra_all":np.arange(99,357),"extra_supported":np.array([i for i in range(99,357) if gold[i]["associated_library_indices"]])}
    fields=["match1","hit5","mrr","macro_recall5"]
    real=evaluate(np.load(ROOT.parent/"rankings.npz")["lex_real"],gold)
    by_seed=[]
    for i,ranks in enumerate(ranked):
        measured=evaluate(ranks,gold)
        for name,ix in sets.items():
            row={"seed":i,"cohort":name,"n":len(ix)}
            for j,k in enumerate(fields):
                row[k]=int(measured[ix,j].sum()) if j<2 else float(measured[ix,j].mean())
            by_seed.append(row)
    out={}
    for name,ix in sets.items():
        out[name]={}
        for j,k in enumerate(fields):
            a=np.array([r[k] for r in by_seed if r["cohort"]==name])
            x=float(real[ix,j].sum() if j<2 else real[ix,j].mean())
            out[name][k]={"real":x,"n_perm":len(a),"min":a.min().item(),
                         "median":float(np.median(a)),"max":a.max().item(),"n_ge_real":int((a>=x-1e-14).sum())}
    if verify:
        assert out==load(ROOT/"results.json")
        with (ROOT/"per_seed.csv").open(encoding="utf8",newline="") as f: archived=list(csv.DictReader(f))
        assert len(archived)==len(by_seed)
        for a,b in zip(archived,by_seed):
            assert all(v==a[k] if isinstance(v,str) else abs(v-float(a[k]))<1e-14 for k,v in b.items())
        print("Verified 64 complete permutation ranks for 357 trials and their reference scores.")
    else:
        (ROOT/"results.json").write_text(json.dumps(out,indent=1),encoding="utf8")
        with (ROOT/"per_seed.csv").open("w",encoding="utf8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(by_seed[0]));w.writeheader();w.writerows(by_seed)
        print(json.dumps(out["lite"]))


if __name__=="__main__":
    import sys
    main("--verify" in sys.argv)

