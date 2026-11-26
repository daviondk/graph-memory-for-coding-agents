"""Transfer a query match to other fragments of the same observed tool call."""
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
from collections import defaultdict
import hashlib
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / "graph_memory_round42/causal_ablation"
sys.path.insert(0, str(BASE))
from core42 import SEEDS, firstfit, read, save, sha
from models42 import portable, trees_for

ARMS = ("baseline", "partners", "permuted", "opposite")
PROTOCOL = "c28f0cd547fd7d406868647f26aea6435a8ccaadaf8f276105c17096b1926c70"


def geometry(meta, trajectory):
    call, chunk, nin, nout = np.rint(np.expm1(meta[:, [8, 2, 10, 11]])).astype(int).T
    role = meta[:, 0].astype(int)
    group = 2 * call + role
    slots = 2 * (1 + max(call))
    sizes = np.bincount(group, minlength=slots)
    assert np.array_equal(sizes[2 * call], nin) and np.array_equal(sizes[2 * call + 1], nout)
    rows = sorted(range(len(group)), key=lambda i: (call[i], role[i], chunk[i]))
    by_call = defaultdict(list)
    by_size = defaultdict(list)
    for i in rows:
        by_call[call[i]].append(i)
    for c, inds in by_call.items():
        by_size[(nin[inds[0]], nout[inds[0]])].append(c)
    perm = np.arange(len(group))
    for calls in by_size.values():
        ordered = sorted(calls, key=lambda c: hashlib.sha256(f"r50-pool|{trajectory}|{c}".encode()).digest())
        for j, c in enumerate(ordered):
            d = ordered[(j + len(ordered) // 2) % len(ordered)]
            perm[by_call[c]] = by_call[d]
    assert np.array_equal(np.sort(perm), np.arange(len(group)))
    assert np.array_equal(role[perm], role) and np.array_equal(chunk[perm], chunk)
    return group, slots, perm


def witnesses(sem, group, slots):
    # Ranks and positions break cosine ties deterministically.
    order = np.lexsort((np.arange(len(group)), -sem[:, 1], -sem[:, 3], group))
    starts = np.r_[0, np.flatnonzero(np.diff(group[order])) + 1]
    ends = np.r_[starts[1:], len(group)]
    leader = np.full(slots, len(group))
    runner = leader.copy()
    first = order[starts]
    leader[group[first]] = first
    pairs = starts[ends - starts > 1]
    runner[group[order[pairs]]] = order[pairs + 1]
    same = np.where(leader[group] == np.arange(len(group)), runner[group], leader[group])
    other = leader[group ^ 1]
    values = np.vstack((sem[:, [3, 1]], [-2., 0.]))
    return np.column_stack((values[same], values[other]))


def features(sem, meta, edge, records):
    same, sham = np.empty((len(sem), 4)), np.empty((len(sem), 4))
    start = swapped = 0
    for _, trajectory, count, _ in records:
        sel = slice(start, start + count)
        groups, slots, perm = geometry(meta[sel], trajectory)
        peer = witnesses(sem[sel], groups, slots)
        same[sel] = peer
        sham[sel] = peer[perm]
        swapped += np.count_nonzero(perm != np.arange(count))
        start += count
    assert start == len(sem)
    base = np.column_stack((sem, meta, edge))
    return dict(baseline=base, partners=np.column_stack((base, same)),
                permuted=np.column_stack((base, sham)), opposite=np.column_stack((base, same[:, 2:]))), swapped


def projection(split, shard):
    source = BASE / f"{split}-{shard}.json.gz"
    data = BASE / f"{split}-{shard}.npz"
    assert read(BASE / f"features-{shard}-seal.json")["rows"][split] == [sha(source), sha(data)]
    with np.load(data) as packed:
        arrays = dict(packed)
    return read(source), arrays


def fit():
    mats = defaultdict(list)
    ys, weights = [], []
    for shard in range(8):
        rows, a = projection("train", shard)
        x, _ = features(a["sem13"], a["meta"], a["edge"], rows)
        pos = 0
        for _, _, n, _ in rows:
            sl = slice(pos, pos + n)
            pos += n
            y = a["labels"][sl].astype(bool)
            if y.any() and not y.all():
                ys.append(y)
                weights.append(np.where(y, 0.5 / y.sum(), 0.5 / (~y).sum()))
                for arm in ARMS:
                    if arm != "baseline":
                        mats[arm].append(x[arm][sl])
    y, w = np.concatenate(ys), np.concatenate(weights)
    assert len(ys) == 1966 and len(y) == 138768
    w *= len(w) / w.sum()
    models = {"baseline": read(BASE / "models.json")["models"]["full"]["hgb"]}
    for arm, chunks in mats.items():
        models[arm] = trees_for(np.concatenate(chunks), y, w)
        print("trained", arm, flush=True)
    save(HERE / "models.json.gz", models)


def predict():
    models = read(HERE / "models.json.gz")
    all_rows = {}
    n_moved = n_items = 0
    for shard in range(8):
        rows, a = projection("test", shard)
        old = read(BASE / f"packets-{shard}.json.gz")
        costs = np.rint(np.expm1(a["meta"][:, 1])).astype(int)
        for seed in SEEDS:
            sem = a[f"sem{seed}"]
            x, moved = features(sem, a["meta"], a["edge"], rows)
            if seed == SEEDS[0]:
                n_moved += moved
                n_items += len(sem)
            scores = {arm: portable(models[arm], xx) for arm, xx in x.items()}
            start = 0
            for q, trajectory, count, ext in rows:
                sl = slice(start, start + count)
                start += count
                ids = np.asarray(ext)
                rank = np.rint(np.expm1(sem[sl, 0])).astype(int)
                packets = {}
                for arm in ARMS:
                    indices = firstfit(np.lexsort((rank, -scores[arm][sl])), costs[sl])
                    packets[arm] = [ids[indices].tolist(), int(costs[sl][indices].sum())]
                assert old[q][1][str(seed)]["hgb/full"] == packets["baseline"][0]
                key = hashlib.sha256(q.encode()).hexdigest()
                all_rows.setdefault(key, [trajectory, {}])[1][str(seed)] = packets
        print("predicted", shard, flush=True)
    assert len(all_rows) == 2000
    save(HERE / "predictions.json.gz", all_rows)
    save(HERE / "forecast-seal.json", dict(model=sha(HERE / "models.json.gz"), protocol=PROTOCOL,
         forecasts=sha(HERE / "predictions.json.gz"), code=sha(Path(__file__)), moved=int(n_moved), rows=int(n_items),
         baseline_matches=2000*len(SEEDS)))


if __name__ == "__main__":
    assert sha(HERE / "PROTOCOL_RU.md") == PROTOCOL
    fit()
    predict()

