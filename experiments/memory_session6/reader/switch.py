"""CPU-only nested grouped switch fitting and symmetric zero-shot external evaluation."""
import collections
import hashlib
import json
import platform
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SEED = 20261118
LAMBDAS = [0.01, 0.1, 1., 10.]
THRESHOLDS = [-.10, -.03, 0., .03, .10]
FILES = ["potential_outcomes.jsonl", "preregistration.md", "source_receipt.json", "prepare.py", "switch.py"]


def fold_ids(groups, k, salt):
    count = collections.Counter(groups)
    def tie(group):
        return hashlib.sha256(f"{SEED}|{salt}|{group}".encode()).hexdigest()
    bin_sizes = [0]*k
    assignment = {}
    for group in sorted(count, key=lambda g: (-count[g],tie(g))):
        fold = min(range(k), key=lambda f: (bin_sizes[f], f))
        assignment[group] = fold
        bin_sizes[fold] += count[group]
    return np.array([assignment[g] for g in groups])


def fit(x, delta, reg):
    mean, std = x.mean(0), x.std(0)
    std[std < 1e-10] = 1
    z = (x - mean)/std
    intercept = delta.mean()
    weights = np.linalg.solve(z.T@z + len(x)*reg*np.eye(z.shape[1]), z.T@(delta-intercept))
    return dict(mean=mean.tolist(), std=std.tolist(), weights=weights.tolist(), intercept=float(intercept))


def gain(model, x):
    return model["intercept"] + ((x-model["mean"])/model["std"])@model["weights"]


def choose(x, outcomes, groups, salt):
    delta = outcomes[:,1,0] - outcomes[:,0,0]
    folds = fold_ids(groups, 4, salt)
    scores = []
    for reg in LAMBDAS:
        est = np.empty(len(x))
        for f in range(4):
            test = folds == f
            assert not set(groups[test]).intersection(groups[~test])
            est[test] = gain(fit(x[~test],delta[~test],reg),x[test])
        for threshold in THRESHOLDS:
            action = est > threshold
            scores.append((round(float(delta[action].sum()),12), -int(action.sum()), reg, threshold, "ridge"))
    scores += [(0.0, 0, float("inf"), float("inf"), "off"),
               (round(float(delta.sum()),12), -len(x), float("inf"), float("inf"), "on")]
    utility, negative_reads, reg, threshold, method = max(scores)
    best = dict(family=method, inner_gain_sum=utility, inner_reads=-negative_reads)
    if method == "ridge":
        best.update(reg=reg, threshold=threshold, parameters=fit(x, delta, reg))
    return best


def apply(rule, x):
    if rule["family"] in {"on","off"}:
        return np.full(len(x),rule["family"]=="on")
    return gain(rule["parameters"], x) > rule["threshold"]


def count_sign(values):
    return {"wins": int(np.sum(values>1e-12)), "losses": int(np.sum(values< -1e-12)),
            "ties": int(np.sum(abs(values)<=1e-12))}


def estimate(outcomes, action, groups):
    n = len(action)
    labels, inv = np.unique(groups, return_inverse=True)
    sampled = np.random.default_rng(SEED).integers(0,len(labels),(10000,len(labels)))
    sizes = np.bincount(inv)[sampled].sum(1)
    out = {"n":n, "groups":len(labels), "reads":int(action.sum()), "saved":int((~action).sum())}
    def group_draw(vals):
        return np.bincount(inv,weights=vals)[sampled].sum(1)/sizes
    for index, metric in enumerate(["primary", "secondary"]):
        off, on = outcomes[:,0,index],outcomes[:,1,index]
        gate = np.where(action,on,off)
        oracle = np.maximum(on,off)
        best = on if on.mean()>off.mean() else off
        boot = group_draw(gate)-np.maximum(group_draw(on),group_draw(off))
        out[metric] = dict(off=float(off.mean()), on=float(on.mean()), gate=float(gate.mean()), oracle=float(oracle.mean()),
              best="on" if best is on else "off", gain=float(gate.mean()-best.mean()),
              ci=np.quantile(boot,[.025,.975]).tolist(), gate_vs_best=count_sign(gate-best),
              on_vs_off=count_sign(on-off), chosen_on_vs_off=count_sign((on-off)[action]),
              skipped_on_vs_off=count_sign((on-off)[~action]))
    return out


def load():
    records = [json.loads(line) for line in (ROOT/"potential_outcomes.jsonl").read_text().splitlines()]
    datasets = {}
    for ds in ["cast","ser"]:
        rows = [r for r in records if r["dataset"]==ds]
        assert len({r["id"] for r in rows}) == len(rows)
        groups = np.array([r["group"] for r in rows])
        x = np.array([r["features"] for r in rows])
        y = np.array([[r[a]["grades"] for a in ["off","on"]] for r in rows])
        fold = np.array([r["fold"] for r in rows]) if ds=="ser" else fold_ids(groups,5,"cast-outer")
        datasets[ds] = rows,groups,x,y,fold
    return datasets


def run():
    datasets=load()
    decisions = {}
    models = {}
    result={}
    state_rows=[]
    for source, (_, groups,x,y,fold) in datasets.items():
        key=source+"_nested"
        action=np.empty(len(x),dtype=bool)
        models[key]={}
        for f in range(5):
            test=fold==f
            assert not set(groups[test]).intersection(groups[~test])
            rule=choose(x[~test],y[~test],groups[~test],f"{source}-inner-{f}")
            models[key][str(f)]=rule
            action[test]=apply(rule,x[test])
        decisions[key]=action
        models[source+"_full"]=choose(x,y,groups,source+"-full-inner")
    for target, (rows,groups,x,y,fold) in datasets.items():
        source="ser" if target=="cast" else "cast"
        key=f"{source}_to_{target}"
        decisions[key]=apply(models[source+"_full"],x)
        for name in (target+"_nested",key):
            action=decisions[name]
            result[name]=estimate(y,action,groups)
            if target=="ser":
                tok=np.array([r["on_tokens"] for r in rows])
                result[name]["on_tokens_per_state"]=float(tok.mean())
                result[name]["gate_tokens_per_state"]=float((tok*action).mean())
            for i,row in enumerate(rows):
                state_rows.append({"evaluation":name,"id":row["id"],"group":row["group"],"fold":int(fold[i]),
                    "action":"on" if action[i] else "off",
                    "chosen_grades":y[i,int(action[i])].tolist(),"on_minus_off":(y[i,1]-y[i,0]).tolist()})
    files = {
        "models.json":json.dumps(models,indent=2),
        "results.json":json.dumps(result,indent=2),
        "decisions.jsonl":"".join(json.dumps(r,separators=(",",":"))+"\n" for r in state_rows)}
    for filename,content in files.items():
        path=ROOT/filename
        if path.exists():
            assert path.read_text(encoding="utf-8")==content, f"replay mismatch in {filename}"
        else:
            path.write_bytes(content.encode())
    receipt = {"python":platform.python_version(), "numpy":np.__version__, "seed":SEED,
               "sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [*FILES,*files]}}
    (ROOT/"replay_receipt.json").write_bytes(json.dumps(receipt,indent=2).encode())
    for k,v in result.items():
        print(k,v["reads"],v["primary"])


if __name__=="__main__":
    run()
