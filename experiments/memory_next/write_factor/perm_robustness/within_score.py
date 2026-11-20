"""Read the relevance join after the within-repository rankings are frozen."""
import csv
import sys
import numpy as np
from predict import ROOT, PRIOR, load, sha, save
from within_predict import table

def main(verify=False):
    locked=load(ROOT/"within_lock.json")
    assert all(sha(ROOT/k)==v for k,v in locked["files"].items())
    tr=PRIOR.parent/"transfer"
    cards=load(PRIOR/"keys.json")
    repo={r["trace_key"]:r["repo"].lower() for r in table(tr/"source_times_lite.csv")}
    repo_ix=np.array([repo[k] for k in cards])
    qs=table(tr/"query_times_lite.csv")
    gold=load(PRIOR/"scoring-inputs.json")[:99]
    ref=np.load(PRIOR/"rankings.npz")
    controls={"real":ref["lex_real"][None,:99],"absent":ref["lex_absent"][None,:99],
              "across":np.load(ROOT/"predictions.npz")["rankings"][:,:99],
              "within":np.load(ROOT/"within_ranks.npz")["rankings"]}
    rows=[]
    for group,ranksets in controls.items():
        for seed,rank in enumerate(ranksets):
            for restrict in (False, True):
                vals=np.zeros(4)
                for i,r in enumerate(rank):
                    selected_repo=qs[i]["repo"].lower()
                    v=r[repo_ix[r]==selected_repo] if restrict else r
                    hit=np.flatnonzero(np.isin(v,gold[i]["associated_library_indices"]))
                    vals += [int(hit.size and hit[0]==0),int(hit.size and hit[0]<5),
                             1/(hit[0]+1) if hit.size else 0.,int(repo_ix[v[0]]==selected_repo)]
                rows.append({"control":group,"same_repo_only":int(restrict),"seed":seed,
                            "match1":int(vals[0]),"hit5":int(vals[1]),"mrr":vals[2]/99,"repo1":int(vals[3])})
    out={}
    for restrict in (0,1):
        part=[r for r in rows if r["same_repo_only"]==restrict]
        out[str(restrict)]={}
        for group in controls:
            out[str(restrict)][group]={}
            for k in ("match1","hit5","mrr","repo1"):
                xs=[r[k] for r in part if r["control"]==group]
                real=next(r[k] for r in part if r["control"]=="real")
                out[str(restrict)][group][k]={"min":min(xs),"median":float(np.median(xs)),"max":max(xs),
                                            "n_ge_real":sum(v>=real-1e-14 for v in xs)}
    if verify:
        assert out==load(ROOT/"within_results.json")
        archived=table(ROOT/"within_per_seed.csv")
        assert len(rows)==len(archived)
        for a,b in zip(archived,rows):
            assert all(v==a[k] if isinstance(v,str) else abs(v-float(a[k]))<1e-12 for k,v in b.items())
        print("Verified all within-repository controls and restricted candidate-pool scores.")
    else:
        save(ROOT/"within_results.json",out)
        with (ROOT/"within_per_seed.csv").open("w",newline="",encoding="utf8") as file:
            w=csv.DictWriter(file,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        for restrict in ("0","1"):
            print(restrict,[(g,r["match1"]) for g,r in out[restrict].items()])

if __name__=="__main__":
    main("--verify" in sys.argv)

