"""Retrain the same out-of-fold classifier under alternative tie-handling rules."""
from pathlib import Path
import hashlib
import gzip
import json
import sys
from collections import Counter
HERE=Path(__file__).resolve().parent
CROSS=HERE.parent/"repo_crossfit"
sys.path.insert(0,str(CROSS))
from fit_crossfit import (R34,get,sha,extract,estimate,certify,labels,rank,order,utility,union_value,
                          dev_scores,best,GRID,serial_model)
from evaluate import score_state
import numpy as np
from scipy.stats import rankdata


def save(name,obj):
    data=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    (HERE/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)


def shuffle_key(q,ids):
    keys=[hashlib.sha256(("r39-tie-null-v1/"+q+"|"+i).encode()).digest() for i in ids]
    return np.array(sorted(range(len(ids)),key=keys.__getitem__))


def fit():
    rows=get(R34/"strong/features.json.gz")
    existing=get(CROSS/"selection.json")
    frozen=get(CROSS/"predictions.json.gz")
    raw=extract(rows)
    groups={}
    audit=Counter()
    for q,X in raw.items():
        n=len(X)
        ids=rows[q]["ids"]
        assert ids==sorted(ids)
        sham=shuffle_key(q,ids)
        add={}
        for rule in ("original","midrank","hashed"):
            xx=X.copy()
            for j in range(15,69,6):
                v=X[:,j]
                if rule=="midrank":
                    rr=rankdata(-v,method="average")
                    xx[:,j+1]=np.log1p(rr)
                    audit["state_fields"]+=1
                    if v.min()==v.max():
                        audit["state_fields_constant"]+=1
                    _,codes,counts=np.unique(v,return_inverse=True,return_counts=True)
                    audit["candidate_fields"]+=n
                    audit["zero_tie_rows"]+=int((v==0).sum()) if (v==0).sum()>1 else 0
                    audit["nonzero_tie_rows"]+=int(np.sum((v!=0)&(counts[codes]>1)))
                    # Stable argsort over the original ID order should recover the published rank.
                    expected=np.asarray(np.log1p(rank(v)),dtype=np.float32)
                    audit["precision_changed_ordinal_rows"]+=int(np.sum(expected!=X[:,j+1]))
                if rule=="hashed":
                    perm=sham[np.argsort(-v[sham],kind="stable")]
                    rr=np.argsort(perm)+1
                    xx[:,j+1]=np.log1p(rr)
            add[rule]=xx
        groups[q]=add
    all_pred={}
    selection={}
    models={}
    for f,split in existing["choices"].items():
        train=set(split["train"]);dev=split["dev"];test=split["test"]
        assert train.isdisjoint(test) and not set(dev)&set(test)
        gold=labels(train|set(dev))
        train_routes=certify(rows,{q:gold[q] for q in train})
        dev_routes=certify(rows,{q:gold[q] for q in dev})
        base=split["trained_baselines"][str(split["choices"]["union"])]
        strength={q:union_value(row,base) for q,row in rows.items()}
        models[f]={}
        selection[f]={}
        for q in test:
            ids=rows[q]["ids"]
            sham=shuffle_key(q,ids)
            all_pred[q]={"id_ascending":ids[:8],"id_descending":list(reversed(ids))[:8],"random":[ids[j] for j in sham[:8]]}
        for mode in ("original","midrank","hashed"):
            features={q:o[mode].copy() for q,o in groups.items()}
            for q,xx in features.items():
                xx[:,3]=np.log1p(rank(strength[q]))
                xx[:,4]=strength[q]
            model,stats=estimate(rows,features,train_routes,"proposed")
            models[f][mode]=serial_model(model)
            values={q:(utility(strength[q]),utility(model.decision_function(features[q]))) for q in dev+test}
            grid={}
            for a in GRID:
                preds={q:order((1-a)*values[q][0]+a*values[q][1])[:8] for q in dev}
                grid[a]=dev_scores(rows,dev_routes,preds)
            alpha=best(grid)
            selection[f][mode]=dict(alpha=alpha,scores=grid,stats=stats)
            for q in test:
                ixs=order((1-alpha)*values[q][0]+alpha*values[q][1])[:8]
                all_pred[q][mode]=[rows[q]["ids"][j] for j in ixs]
                if mode=="original":
                    assert all_pred[q][mode]==frozen[q]["proposed"],q
    assert len(all_pred)==494
    save("models.json.gz",models)
    save("selection.json",dict(folds=selection,training_diagnostics=dict(audit)))
    save("predictions.json.gz",all_pred)
    save("seal.json",{p:sha(HERE/p) for p in ("PROTOCOL_RU.md","audit.py","models.json.gz","selection.json","predictions.json.gz")})
    print("Frozen",len(all_pred),"states and all 494 original top-eight controls matched.")


def grade():
    for f,v in get(HERE/"seal.json").items():
        assert sha(HERE/f)==v
    forecast=get(HERE/"predictions.json.gz")
    rows=get(R34/"strong/features.json.gz")
    gold=labels(set(forecast))
    out={q:dict(repo=rows[q]["repo"],metrics=score_state(rows[q],gold[q],arms)) for q,arms in forecast.items()}
    save("outcomes.json.gz",out)
    import importlib.util
    src=HERE.parent/"author_baseline"
    sys.path.insert(0,str(src))
    spec=importlib.util.spec_from_file_location("contrast_ledger",src/"grade.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    res=module.summarize(out,"midrank")
    res["seal"]=sha(HERE/"seal.json")
    res["bootstrap_module"]=sha(src/"grade.py")
    save("results.json",res)
    print(res["successes"])


if __name__=="__main__":
    if sys.argv[1]=="fit":
        fit()
    else:
        grade()
