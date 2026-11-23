"""Verify the packaged predictions and native group metrics, independent of source texts."""
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import score
HERE=Path(__file__).resolve().parent

def auc(y,s):
    # Mann-Whitney: sum ranks for positive observations, ties averaged.
    from scipy.stats import rankdata
    p=int(y.sum())
    if p in (0,len(y)):
        return None
    return (rankdata(s,method="average")[y].sum()-p*(p+1)/2)/(p*(len(y)-p))

def close(x,y):
    if x is None:
        assert y is None
    else:
        assert abs(x-y)<1e-12,(x,y)

def main():
    man=HERE/"MANIFEST_SHA256.json"
    if man.exists():
        regs=score.read(man)
        assert set(regs)=={p.name for p in HERE.iterdir() if p.is_file() and p!=man}
        assert all(hashlib.sha256((HERE/p).read_bytes()).hexdigest()==v for p,v in regs.items())
    split=score.read(HERE/"split.json")["folds"]
    metrics=score.read(HERE/"group-metrics.json.gz")
    gold={}
    for p in HERE.glob("gold-*-of-*.json.gz"):
        d=score.read(p)
        assert not set(gold)&set(d)
        gold.update(d)
    total=0
    for i,f in enumerate(split):
        a=score.read(HERE/f"fold-{i:02d}.json")
        assert not set(f["train"])&set(f["test"]) and a["train_test_session_intersection"]==0
        assert a["remaining_normalized_train_test_intersection"]==0
        assert a["n_train_before"]==a["train_remaining"]+a["removed_train_pos"]+a["removed_train_neg"]
        for row in score.read(HERE/f"pred-{i:02d}.json.gz"):
            k=row["id"]
            y=np.array(gold[k],dtype=bool)
            u=np.asarray(row["user"],dtype=bool)
            p=int(y.sum())
            assert metrics[k]["p"]==p and metrics[k]["n"]==len(y)
            for arm in score.ARMS:
                got=metrics[k]["arms"][arm]
                s=np.array(row["score"][arm]) if arm in row["score"] else (u.astype(float) if arm=="user_first" else np.zeros(len(u)))
                close(auc(y,s),got["auc"])
                order=np.argsort(-s)
                for b in score.BUDGET:
                    n=math.ceil(b*len(y))
                    # Analytical expectation under uniformly shuffled ties at the cutoff for the two controls.
                    if arm in row["score"]:
                        hit=y[order[:n]].sum()
                    else:
                        cut=s[order[n-1]]
                        above=s>cut
                        eq=s==cut
                        hit=y[above].sum()+(n-above.sum())*y[eq].sum()/eq.sum()
                    close(hit/p if p else None,got["R"+str(round(100*b))])
                total+=1
    # Re-score aggregate results in idempotent mode, byte-comparing existing output documents.
    score.run()
    assert total==3500
    print("PASS: 500 histories x 7 scorers, all four metrics and SHA-256; paired aggregates reproduced.")
if __name__=="__main__":
    main()
