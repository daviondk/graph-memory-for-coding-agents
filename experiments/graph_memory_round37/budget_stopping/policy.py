"""Learn and freeze a reading cutoff before loading test supervision."""
import gzip
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

D = Path(__file__).resolve().parent
WORK = D.parents[1]
CAL = WORK / "graph_memory_round35/calibration_scale"
ATOMS = WORK / "graph_memory_round34/interval_witness"
PRIVATE = Path("D:/CodexResearch/x20-r33-budget-loss")
BUDGET = 2048
ALPHAS = (1, 5, 10)
RULES = ("tokens", "nodes", "fraction", "drop", "learned")

def load(path):
    binary = path.read_bytes()
    return json.loads(gzip.decompress(binary) if path.suffix == ".gz" else binary)

def save(name, data):
    binary = (json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()
    if name.endswith(".gz"):
        binary = gzip.compress(binary, mtime=0)
    (D / name).write_bytes(binary)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def linear(model, x):
    return x @ model["coef"] + model["intercept"]

def row(z, costs, offset, model):
    s = offset + ((z - model["center"]) / model["scale"]) @ model["weights"]
    order = np.argsort(-s, kind="stable")
    cum = np.cumsum(costs[order])
    k = int(cum.searchsorted(BUDGET, side="right"))
    prefix = order[:k]
    spent = np.r_[0, cum[:k]].astype(int)
    drop = s[order[0]] - s[prefix]
    features = [np.log1p(len(z)), k, spent[-1] / BUDGET]
    for rank in (0, 1, 3, 7):
        j = order[min(rank, len(order)-1)]
        features.extend((np.log1p(costs[j]), s[order[0]] - s[j], z[j, 0], z[j, 2]))
    features.extend((float(np.mean(z[prefix, 2])) if k else 0., float(drop[-1]) if k else 0.,
                     float(np.quantile(s, .75)-np.quantile(s, .25))))
    return dict(order=prefix, spent=spent, drop=drop, features=features)

def fit(model):
    inv = load(CAL / "train-inventory.json")
    numeric = CAL / "numeric-train.npz"
    assert sha(numeric) == inv["npz"]
    folds = load(CAL / "fold-models.json")["folds"]
    with np.load(numeric) as ar:
        g, z, c, y = [ar[k] for k in ("g","z","c","y")]
    X, target = [], []
    start = 0
    for q in inv["order"]:
        rec = inv["records"][q]
        n = rec["n"]
        sl = slice(start, start+n)
        fold = folds[str(rec["fold"])]
        r = np.arange(1, n+1)
        rx = np.column_stack((-np.log(r), 1/r, (n-r)/max(1,n-1)))
        offset = linear(fold["graph_model"],g[sl]) + linear(fold["rank_model"],rx)
        item = row(z[sl],c[sl],offset,model)
        positive = np.flatnonzero(y[sl][item["order"]])
        target.append(int(item["spent"][positive[-1]+1]) if len(positive) else 0)
        X.append(item["features"])
        start += n
    assert start == len(g) and len(X) == 3894
    estimator = GradientBoostingRegressor(loss="quantile", alpha=.9, n_estimators=100, max_depth=2,
        min_samples_leaf=30, learning_rate=.05, random_state=37012).fit(X, target)
    trees = []
    for tree in estimator.estimators_[:,0]:
        t = tree.tree_
        trees.append(dict(left=t.children_left.tolist(),right=t.children_right.tolist(),feature=t.feature.tolist(),
                          threshold=t.threshold.tolist(),value=t.value.ravel().tolist()))
    exported = dict(intercept=float(estimator.init_.constant_.item()),rate=.05,trees=trees)
    save("model.json",exported)
    assert np.allclose([predict(exported,x) for x in X],estimator.predict(X),atol=1e-8,rtol=0)
    return exported

def predict(model, x):
    features = np.asarray(x, dtype=np.float32)
    value = model["intercept"]
    for tree in model["trees"]:
        j = 0
        while tree["left"][j] >= 0:
            child = "left" if features[tree["feature"][j]] <= tree["threshold"][j] else "right"
            j = tree[child][j]
        value += model["rate"] * tree["value"][j]
    return value

def blind(stage, model, tree):
    path = PRIVATE/(stage+".json.gz")
    prior = WORK/"graph_memory_round33/budget_loss"/(stage+"-input.json")
    assert sha(path) == load(prior)["features"]
    expected = load(CAL/(stage+"-orders.json.gz"))
    rows = {}
    for raw in load(path):
        q = raw["q"]
        z = np.array(raw["x"])
        item = row(z, np.array(raw["c"]), np.array(raw["o"]), model)
        assert np.array_equal(item["order"],expected[q]["oof_3894"][:len(item["order"])])
        item.update(t=raw["t"],pred=predict(tree,item["features"]))
        rows[q] = item
    return rows

def atomic_trace(item, atoms):
    rank = {i:k for k,i in enumerate(item["order"],1)}
    k = len(rank)
    mass = np.zeros(k+2, dtype=int)
    for _,lo,hi,indices in atoms:
        first = min((rank[i] for i in indices if i in rank),default=k+1)
        mass[first] += hi-lo
    target = int(np.flatnonzero(mass[:k+1])[-1]) if mass[:k+1].any() else 0
    return target, np.cumsum(mass[:-1]), int(mass.sum())

def requirements(item, k):
    prefix = item["spent"]
    y = int(prefix[k])
    return dict(tokens=y,nodes=k,fraction=y/max(1,int(prefix[-1])),
                drop=float(item["drop"][k-1]) if k else -1.,learned=y-item["pred"])

def fit_thresholds(rows, atoms, alpha):
    maxima = defaultdict(dict)
    for q,item in rows.items():
        target,_,_ = atomic_trace(item,atoms[q])
        group = maxima[item["t"]]
        for rule,value in requirements(item,target).items():
            group[rule] = max(group.get(rule,-math.inf),value)
    rank = math.ceil((len(maxima)+1)*(1-alpha/100))
    assert rank <= len(maxima)
    return {rule:float(sorted(x[rule] for x in maxima.values())[rank-1]) for rule in RULES}

def cutoff(item, rule, threshold):
    k = len(item["order"])
    if rule == "nodes":
        return min(k,max(0,int(threshold)))
    if rule == "drop":
        return int(item["drop"].searchsorted(threshold,side="right"))
    cost = threshold
    if rule == "learned":
        cost += item["pred"]
    if rule == "fraction":
        cost *= item["spent"][-1]
    cap = min(BUDGET,max(0,math.ceil(cost)))
    return int(item["spent"][1:].searchsorted(cap,side="right"))

def matched(rows, thresholds):
    goal = sum(r["spent"][cutoff(r,"learned",thresholds["learned"])] for r in rows.values())
    # Histogram of marginal token increments yields the total delivered at every constant cap.
    change = np.zeros(BUDGET+1,dtype=int)
    for r in rows.values():
        np.add.at(change,r["spent"][1:],np.diff(r["spent"]))
    return int(np.argmin(np.abs(np.cumsum(change)-goal)))

def freeze():
    model = load(CAL/"models.json")["models"]["oof_3894"]
    tree = fit(model)
    dev = blind("dev",model,tree)
    test = blind("test",model,tree)
    assert not ({r["t"] for r in dev.values()} & {r["t"] for r in test.values()})
    atoms = load(ATOMS/"dev-atoms.json.gz")
    thresholds = {str(alpha):fit_thresholds(dev,atoms,alpha) for alpha in ALPHAS}
    match = matched(dev,thresholds["5"])
    save("selection.json",dict(thresholds=thresholds,matched_dev_cap=match,fit=sha(D/"model.json"),
         train=sha(CAL/"numeric-train.npz"),dev_labels=sha(ATOMS/"dev-atoms.json.gz"),
         code=sha(D/"policy.py"),protocol=sha(D/"PROTOCOL_RU.md")))
    for stage,rows in (("dev",dev),("test",test)):
        forecast = {}
        for q,r in rows.items():
            arms = {"full":len(r["order"]),"matched":cutoff(r,"tokens",match)}
            for alpha,values in thresholds.items():
                arms.update({rule+"_"+alpha:cutoff(r,rule,value) for rule,value in values.items()})
            forecast[q] = dict(t=r["t"],order=r["order"].tolist(),spent=r["spent"].tolist(),arms=arms)
        save(stage+"-forecast.json.gz",forecast)
    save("seal.json",dict(selection=sha(D/"selection.json"),dev=sha(D/"dev-forecast.json.gz"),
                          test=sha(D/"test-forecast.json.gz")))
    print("Frozen",len(dev),len(test),match,thresholds["5"])
if __name__ == "__main__":
    freeze()

