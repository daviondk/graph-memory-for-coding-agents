"""Generate nested out-of-fold forecasts and select all parameters exclusively on inner dev."""
from public import *
from sklearn.ensemble import HistGradientBoostingClassifier
import sklearn
sys.path.insert(0, str(R34))
from experiment import optimize
from data import labels

GRID = (0, .25, .5, .75, 1.)
REG = (.03, .3)


def utility(values):
    return -np.log(rank(values))


def dev_scores(rows, routes, ranks):
    result = np.zeros(3, dtype=int)
    for q, seq in ranks.items():
        seq = seq[:8]
        costs = np.cumsum(np.array(rows[q]["qw"])[seq])
        subsets = (seq[:5], seq, seq[costs <= 2048])
        result += [any(a.issubset(s) for a in routes[q]) for s in subsets]
    return result.tolist()


def best(options):
    return max(options, key=lambda k: (*options[k], -k))


def union_value(row, model):
    return np.array(row["off"]) + (np.array(row["x"]) - model["center"]) / model["scale"] @ model["weights"]


def certify(rows, labels_subset):
    return {q: sets_native(rows[q]["ids"], label) for q, label in labels_subset.items()}


def estimate(rows, features, certificates, mode):
    blocks, ys, weights = [], [], []
    for q in sorted(certificates):
        routes = certificates[q]
        if not routes:
            continue
        n = len(rows[q]["ids"])
        if mode == "all_routes":
            positive = set().union(*routes)
            y = np.array([j in positive for j in range(n)])
        else:
            y = target(routes, (), n)
        if y is None or not y.any() or y.all():
            continue
        xx = features[q].copy()
        if mode == "no_observed":
            xx[:, 11] = 0
        blocks.append(xx)
        ys.append(y)
        weights.append(np.where(y, .5/y.sum(), .5/(~y).sum()))
    X, Y, W = np.vstack(blocks), np.concatenate(ys), np.concatenate(weights)
    W *= len(W) / W.sum()
    model = HistGradientBoostingClassifier(max_iter=65, learning_rate=.09, max_leaf_nodes=7, min_samples_leaf=55,
                l2_regularization=4, early_stopping=False, random_state=39013).fit(X, Y, sample_weight=W)
    return model, {"states":len(blocks), "rows":len(Y), "positives":int(Y.sum())}


def serial_model(model):
    fields = ("value","is_leaf","feature_idx","num_threshold","missing_go_to_left","left","right")
    return {"base":float(model._baseline_prediction.item()),
            "trees":[{k:layer[0].nodes[k].tolist() for k in fields} for layer in model._predictors]}


def train_fold(rows, raw, folds, fold):
    train = sorted(q for q, r in rows.items() if folds[r["repo"]] not in (fold, (fold+1)%5))
    dev = sorted(q for q, r in rows.items() if folds[r["repo"]] == (fold+1)%5)
    test = sorted(q for q, r in rows.items() if folds[r["repo"]] == fold)
    held = dev + test
    assert len(set(train) | set(dev) | set(test)) == len(train) + len(dev) + len(test) == len(rows)
    gold = labels(set(train + dev))
    assert gold.keys() == set(train + dev) and gold.keys().isdisjoint(test)
    routes = certify(rows, gold)
    dev_routes = {q:routes[q] for q in dev}
    train_routes = {q:routes[q] for q in train}
    base_models, values = {}, {}
    base_scores = {"union":{}, "union_seen":{}}
    for reg in REG:
        base_models[reg] = optimize({q:rows[q] for q in train}, {q:gold[q] for q in train}, "union_cost", reg)
        values[reg] = {q:union_value(r, base_models[reg]) for q, r in rows.items()}
        for name in base_scores:
            dev_ranks = {q:order(values[reg][q] - (1e5*raw[q][:,11] if name == "union_seen" else 0))[:8] for q in dev}
            base_scores[name][reg] = dev_scores(rows, dev_routes, dev_ranks)
    choice = {name:best(scores) for name, scores in base_scores.items()}
    union = values[choice["union"]]
    features = {}
    for q, xx in raw.items():
        features[q] = xx.copy()
        features[q][:, 3] = np.log1p(rank(union[q]))
        features[q][:, 4] = union[q]
    result = {}
    for q in test:
        dense = -np.array(rows[q]["ranks"]["dense_state"], dtype=float)
        seen = raw[q][:, 11]
        result[q] = {"bge":order(dense)[:8], "bge_seen":order(dense-1e5*seen)[:8], "union":order(union[q])[:8],
                     "union_seen":order(values[choice["union_seen"]][q] - 1e5*seen)[:8]}
    scores = {}
    trees = {}
    for mode in ("proposed", "no_observed", "all_routes"):
        model, stats = estimate(rows, features, train_routes, mode)
        trees[mode] = serial_model(model)
        prepared = {}
        for q in held:
            xx = features[q].copy()
            if mode == "no_observed":
                xx[:,11] = 0
            prepared[q] = utility(union[q]), utility(model.decision_function(xx))
        score = {}
        for alpha in GRID:
            seq = {q:order((1-alpha)*prepared[q][0] + alpha*prepared[q][1])[:8] for q in dev}
            score[alpha] = dev_scores(rows, dev_routes, seq)
        a = best(score)
        for q in test:
            result[q][mode] = order((1-a)*prepared[q][0] + a*prepared[q][1])[:8]
        scores[mode] = {"dev":score,"alpha":a,"training":stats}
    for q, options in result.items():
        for mode, values_ in options.items():
            options[mode] = [rows[q]["ids"][j] for j in values_]
            assert len(set(options[mode])) == len(options[mode]) == 8
    selection = dict(train=train, dev=dev, test=test, choices=choice, baselines=base_scores, candidates=scores,
                     trained_baselines=base_models)
    return result, selection, trees


def main():
    inputs = R34 / "strong/features.json.gz"
    assert sha(inputs) == get(R34/"strong/input.json")["features"]
    rows = get(inputs)
    assert len(rows) == 494
    raw = extract(rows)
    folds = fold_by_repository(rows)
    all_predictions, all_selections, all_models = {}, {}, {}
    for fold in range(5):
        result, selections, trees = train_fold(rows, raw, folds, fold)
        assert all_predictions.keys().isdisjoint(result)
        all_predictions.update(result)
        all_selections[fold] = selections
        all_models[fold] = trees
        print("Frozen fold", fold, "states", len(result), flush=True)
    assert all_predictions.keys() == rows.keys()
    write("selection.json", {"folds":folds,"choices":all_selections,"sklearn":sklearn.__version__})
    write("predictions.json.gz", all_predictions)
    write("models.json.gz", all_models)
    artifacts = ("fit_crossfit.py","public.py","PROTOCOL_RU.md","selection.json","predictions.json.gz","models.json.gz")
    dependencies = [inputs, SET_READER/"data.py", R34/"experiment.py", R34/"prepare.py", PUB/"items.jsonl.gz",
                    UP/"dense_inputs.jsonl.gz", UP/"dense_vectors.npy", PUB/"labels.jsonl.gz"]
    write("seal.json", {"local":{p:sha(ROOT/p) for p in artifacts},
                        "dependencies":{p.relative_to(WORK).as_posix():sha(p) for p in dependencies}})


if __name__ == "__main__":
    main()
