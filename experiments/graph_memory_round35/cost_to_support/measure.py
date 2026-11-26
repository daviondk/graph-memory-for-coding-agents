"""Measure the strict prefix price of complete source-span coverage for frozen readers."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np

HERE = Path(__file__).resolve().parent
SERIES = HERE.parent
WORK = SERIES.parent
SEEDS = (13, 17, 29, 37, 41)
ARMS = ("original_R33", "oof_3894")
BUDGETS = np.array([256, 512, 1024, 2048, 4096, 8192])

def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def save(path, value):
    data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    path.write_bytes(gzip.compress(data, mtime=0) if path.suffix == ".gz" else data)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check_parents():
    parents = [WORK/"graph_memory_round34/interval_witness"/"test-atoms.json.gz",
               SERIES/"calibration_scale"/"test-orders.json.gz", SERIES/"calibration_transfer"/"outcomes.json.gz"]
    for shard in range(8):
        parents.extend([WORK/f"graph_memory_round19/trained_rank/forecasts-main-{shard}.json.gz",
                        SERIES/f"calibration_transfer/orders-{shard}.json.gz"])
    save(HERE/"inputs.json", {"files": {p.relative_to(WORK).as_posix(): digest(p) for p in parents},
                              "protocol": digest(HERE/"PROTOCOL_RU.md"), "code": digest(Path(__file__))})

def cost_to_support(order, costs, atoms, covers):
    n = len(costs)
    assert sorted(order) == list(range(n))
    positions = np.empty(n, dtype=int)
    positions[order] = np.arange(n)
    end = max(min(int(positions[node]) for node in group) for *_,group in atoms)
    price = sum(costs[node] for node in order[:end+1])
    # Independent streaming union. The first complete prefix must have the same length and price.
    observed = set()
    total = 0
    for pos, node in enumerate(order):
        total += costs[node]
        observed.update(covers.get(node, ()))
        if len(observed) == len(atoms):
            assert (pos, total) == (end, price)
            return price
    raise ValueError("Uncovered source atom")

def rows():
    atoms = read(WORK/"graph_memory_round34/interval_witness/test-atoms.json.gz")
    original = read(SERIES/"calibration_scale/test-orders.json.gz")
    outcomes = read(SERIES/"calibration_transfer/outcomes.json.gz")
    out = {}
    for shard in range(8):
        orders = read(SERIES/f"calibration_transfer/orders-{shard}.json.gz")
        for record in read(WORK/f"graph_memory_round19/trained_rank/forecasts-main-{shard}.json.gz"):
            q = record["q"]
            costs = [node["token_count"] for node in record["rr"]]
            assert all(v > 0 for v in costs) and q not in out
            groups = atoms[q]
            covers = {}
            for i, (_, left, right, nodes) in enumerate(groups):
                assert left < right and nodes
                for node in nodes: covers.setdefault(node, []).append(i)
            byseed = {"13": original[q], **orders[q]}
            thresholds = []
            for seed in SEEDS:
                pair = []
                for method in ARMS:
                    price = cost_to_support(byseed[str(seed)][method], costs, groups, covers)
                    ys = (price <= BUDGETS).astype(float)
                    native = outcomes[q]["seeds"][str(seed)][method]
                    assert int(ys[3]) == native[0] and math.isclose((ys[:-1]+ys[1:]).mean()/2, native[2], abs_tol=1e-9)
                    pair.append(price)
                thresholds.append(pair)
            out[q] = {"trajectory": record["t"], "costs": thresholds}
    assert len(out) == 2000
    save(HERE/"thresholds.json.gz", out)
    return out

def summarize(out, indices):
    ids = sorted(out)
    values = np.asarray([out[q]["costs"] for q in ids])[:, indices]
    trajectories, group = np.unique([out[q]["trajectory"] for q in ids], return_inverse=True)
    size = np.bincount(group)
    assert len(trajectories) == 1207
    capped = np.minimum(values, 8192)
    clipped = np.clip(values, 256, 8192)
    log_area = 100 * np.log(8192 / clipped) / np.log(32)
    linear_area = 100 * (8192-clipped)/(8192-256)
    effects = np.stack((capped[:,:,0]-capped[:,:,1], values[:,:,0]-values[:,:,1],
                        log_area[:,:,1]-log_area[:,:,0], linear_area[:,:,1]-linear_area[:,:,0]), axis=2)
    n, seeds, metrics = effects.shape
    totals = np.zeros((len(size), seeds, metrics))
    np.add.at(totals, group, effects)
    random = np.random.default_rng(350810)
    fixed, crossed = [], []
    for _ in range(100):
        resampled = random.integers(len(size), size=(100, len(size)))
        counts = np.stack([np.bincount(ix, minlength=len(size)) for ix in resampled])
        means = (counts@totals.reshape(len(size), -1)).reshape(100, seeds, metrics) / (counts@size)[:,None,None]
        fixed.append(means.mean(1))
        ix = random.integers(seeds, size=(100, seeds))
        crossed.append(means[np.arange(100)[:, None], ix].mean(1))
    interval = lambda series: np.quantile(np.concatenate(series), [.025,.975], axis=0).tolist()
    lower, same = values[:,:,1] < values[:,:,0], values[:,:,1] == values[:,:,0]
    return {"seeds": [SEEDS[i] for i in indices], "arms": list(ARMS), "mean_cost": values.mean((0,1)).tolist(),
            "median_cost": np.median(values, axis=(0,1)).tolist(), "mean_capped": capped.mean((0,1)).tolist(),
            "N": n*seeds, "lower_equal_higher": [int(lower.sum()), int(same.sum()), int((~(lower|same)).sum())],
            "log_area": log_area.mean((0,1)).tolist(), "linear_area": linear_area.mean((0,1)).tolist(),
            "effects": effects.mean((0,1)).tolist(), "ci_fixed": interval(fixed), "ci_crossed": interval(crossed)}

if __name__ == "__main__":
    check_parents()
    observations = rows()
    panels = {"transfer4": [1,2,3,4], "all5": [0,1,2,3,4], **{str(s):[i] for i,s in enumerate(SEEDS)}}
    save(HERE/"results.json", {"metrics":["capped_token_saving","uncapped_token_saving","log_uniform_gain_pp","uniform_gain_pp"],
                               "panels":{k:summarize(observations,ix) for k,ix in panels.items()},
                               "cost_rows":digest(HERE/"thresholds.json.gz"), "inputs":digest(HERE/"inputs.json")})

