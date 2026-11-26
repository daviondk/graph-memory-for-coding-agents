"""Reuse the frozen eight-group projection from R45; change only the numeric reader."""
from study import ARMS, BASE, HERE, SEEDS, features, firstfit, portable, read, save, sha
import hashlib
import sys
import numpy as np
sys.path.insert(0, str(BASE.parents[1] / "graph_memory_round45/flow_likelihood"))
import fixed as projection

TRIGGER_HASH = "11ec5c8e673a2acb4e8d2f6f6fe2337d8cb6837a84bd91d1943d1e52914ad515"


def score(records, meta, edge, seeds, models, refs):
    out = {}
    costs = np.rint(np.expm1(meta[:,1])).astype(int)
    for seed, sem in seeds.items():
        xs, _ = features(sem, meta, edge, records)
        scores = {arm: portable(models[arm], x) for arm, x in xs.items()}
        start = 0
        for q,t,n,idx in records:
            sl = slice(start,start+n)
            start += n
            rank = np.rint(np.expm1(sem[sl,0])).astype(int)
            ids = np.asarray(idx)
            picks = {}
            for arm in ARMS:
                ix = firstfit(np.lexsort((rank,-scores[arm][sl])),costs[sl])
                picks[arm] = [ids[ix].tolist(),int(costs[sl][ix].sum())]
            by_id = dict(zip(idx, costs[sl]))
            for source in ("native","rich"):
                items = refs[q][str(seed)][source]
                picks[source] = [items,int(sum(by_id[i] for i in items))]
            out.setdefault(q,[t,True,{}])[2][str(seed)] = picks
    return out


def seal(prefix, files):
    assert prefix == "trigger" and len(files) == 8
    rows = {}
    for file in files:
        for q,(t,yes,sets) in read(file).items():
            key = hashlib.sha256(q.encode()).hexdigest()
            assert key not in rows
            rows[key] = [t,yes,sets]
    assert len(rows) == 2000
    save(HERE / "trigger-predictions.json.gz", rows)
    save(HERE / "trigger-seal.json", dict(protocol=TRIGGER_HASH, code=sha(HERE / "trigger.py"),
          study=sha(HERE/"study.py"),model=sha(HERE/"models.json.gz"), files={p.name:sha(p) for p in files},
          forecasts=sha(HERE/"trigger-predictions.json.gz")))


if __name__ == "__main__":
    assert sha(HERE/"TRIGGER_PROTOCOL_RU.md") == TRIGGER_HASH
    assert sha(projection.D / "fixed.py") == read(projection.D / "manifest.json")["files"]["fixed.py"]
    projection.D = HERE
    projection.weights = lambda: read(HERE / "models.json.gz")
    projection.score = score
    projection.freeze = seal
    projection.main()

