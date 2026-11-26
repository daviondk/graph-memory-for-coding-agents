"""Evaluate the sealed nested predictions using the reference scorer; resample whole repositories."""
from public import *
from data import labels


METRICS = ["MSS@5","MSS@8","MSS@8/2048","MSS@8/6144"]
METHODS = ["bge","bge_seen","union","union_seen","no_observed","all_routes","proposed"]


def score_state(row, label, methods):
    ids = row["ids"]
    cost = dict(zip(ids,row["qw"]))
    routes = sets_native(ids, label)
    ordinal = {k:j for j,k in enumerate(ids)}
    old = native.ideal_group_dcg
    memo = {}
    def ideal(groups, weights, k):
        if k not in memo:
            memo[k] = old(groups, weights, k)
        return memo[k]
    native.ideal_group_dcg = ideal
    result = {}
    try:
        scores = {}
        for method, prediction in methods.items():
            assert len(prediction) == len(set(prediction)) == 8
            cumulative = np.cumsum([cost[x] for x in prediction])
            budgets = [5,8,int((cumulative<=2048).sum()),int((cumulative<=6144).sum())]
            values = []
            for i, top in enumerate(budgets):
                seq = tuple(prediction[:top])
                k = 5 if i == 0 else 8
                if (seq,k) not in scores:
                    scores[seq,k] = int(native.score_prediction(seq,label,k)[f"mss_complete@{k}"])
                    assert scores[seq,k] == any(a.issubset(ordinal[x] for x in seq) for a in routes)
                values.append(scores[seq,k])
            result[method] = values
    finally:
        native.ideal_group_dcg = old
    return result


def main():
    seal = get(ROOT/"seal.json")
    for name, expected in seal["local"].items():
        assert sha(ROOT/name) == expected
    rows = get(R34/"strong/features.json.gz")
    selections = get(ROOT/"selection.json")
    pred = get(ROOT/"predictions.json.gz")
    truth = labels(set(pred))
    assert truth.keys() == pred.keys() == rows.keys() and len(rows) == 494
    qs = sorted(rows)
    out = {}
    for q in qs:
        fold = selections["folds"][rows[q]["repo"]]
        s = selections["choices"][str(fold)]
        assert q in s["test"] and q not in s["dev"] and q not in s["train"]
        assert set(pred[q]) == set(METHODS)
        out[q] = {"fold":fold,"repo":rows[q]["repo"],"metrics":score_state(rows[q], truth[q], pred[q])}
    write("outcomes.json.gz",out)
    names, repo_indices = np.unique([out[q]["repo"] for q in qs], return_inverse=True)
    counts = np.bincount(repo_indices)
    folds = np.array([out[q]["fold"] for q in qs])
    M = np.array([[out[q]["metrics"][s] for s in METHODS] for q in qs], dtype=int)
    R = np.zeros((len(names), len(METHODS), len(METRICS)))
    np.add.at(R, repo_indices, M)
    per_repo = R / counts[:,None,None]
    rng = np.random.default_rng(390637)
    draw = rng.integers(len(names),size=(10000,len(names)))
    W = np.stack([np.bincount(idx, minlength=len(names)) for idx in draw])
    comparisons = {}
    for alt in METHODS[:-1]:
        j = METHODS.index(alt)
        diff = M[:,-1] - M[:,j]
        dr = R[:,-1] - R[:,j]
        dm = per_repo[:,-1] - per_repo[:,j]
        micro = (W @ dr) / (W @ counts)[:,None]
        macro = (W @ dm) / len(names)
        comparisons[alt] = {"micro":diff.mean(0).tolist(),"macro":dm.mean(0).tolist(),
                            "micro95":np.quantile(micro,[.025,.975],axis=0).tolist(),
                            "macro95":np.quantile(macro,[.025,.975],axis=0).tolist(),
                            "wins":(diff>0).sum(0).tolist(),"losses":(diff<0).sum(0).tolist(),
                            "fold_delta":{f:diff[folds==f].mean(0).tolist() for f in range(5)}}
    result = {"metrics":METRICS,"states":len(qs),"repos":len(names),"methods":{},
              "perFoldSizes":{f:int((folds==f).sum()) for f in range(5)},
              "perFoldRepos":{f:sum(v==f for v in selections["folds"].values()) for f in range(5)},
              "pairedProposedMinusControl":comparisons,"bootstrap":10000,"seed":390637,
              "seal":sha(ROOT/"seal.json"),"outcomes":sha(ROOT/"outcomes.json.gz"),"scorer":sha(Path(native.__file__))}
    for i,s in enumerate(METHODS):
        result["methods"][s] = {"success":M[:,i].sum(0).tolist(),"micro":M[:,i].mean(0).tolist(),
                                "macro":per_repo[:,i].mean(0).tolist(),
                                "folds":{f:M[folds==f,i].sum(0).tolist() for f in range(5)}}
    write("results.json",result)
    print("Completed",len(qs),"states",len(names),"repositories.")
    print({s:r["success"] for s,r in result["methods"].items()})


if __name__ == "__main__":
    main()
