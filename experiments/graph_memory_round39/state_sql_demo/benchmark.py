"""Verify every public state and time paired, reversible observation changes."""
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import json
import platform
import sqlite3
from statistics import median
from time import perf_counter_ns
from reader import D, Reader, Grader

R = D.parent/"set_reader"
UP = D.parents[1]/"memory_session5/serbench/upstream"


def read(p):
    b = p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix == ".gz" else b)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hashed(s):
    return hashlib.sha256(s.encode()).hexdigest()


def stats(ns):
    ordered = sorted(x/1000 for x in ns)
    pos = (len(ns)-1)*.95
    i = int(pos)
    return dict(n=len(ns), median_us=median(ordered), p95_us=ordered[i]+(ordered[min(i+1,len(ns)-1)]-ordered[i])*(pos-i))


def official_scorer():
    p = UP/"src/serbench/_reference_scorer.py"
    assert read(R/"results.json")["native"] == sha(p)
    spec = importlib.util.spec_from_file_location("serbench_ref",p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    assert all(sha(D/f)==digest for f,digest in read(D/"build.json")["files"].items())
    seal = read(R/"seal.json")
    assert sha(R/"predictions.json.gz") == seal["predictions"] and sha(UP/"data/cal500/items.jsonl.gz") == seal["items"]
    predictions = read(R/"predictions.json.gz")
    with gzip.open(UP/"data/cal500/labels.jsonl.gz", "rt", encoding="utf-8") as f:
        labels = {r["state_id"]:r for r in map(json.loads,f) if r["state_id"] in predictions}
    keys = {hashed(q):q for q in predictions}
    tic = perf_counter_ns()
    indexed = Reader()
    load_ms = (perf_counter_ns()-tic)/1e6
    fresh, grader = Reader(), Grader()
    native = official_scorer()
    original_ideal = native.ideal_group_dcg
    records, baselines, checks = [], {}, Counter()
    plans = {}
    from reader import TOP, FRESH
    for name, sql in (("indexed",TOP),("full",FRESH)):
        plans[name] = list(indexed.db.execute("EXPLAIN QUERY PLAN "+sql, ("s001",8)))
    for ix,state in enumerate(indexed.states()):
        state_digest = indexed.db.execute("SELECT state_digest FROM state WHERE state=?", (state,)).fetchone()[0]
        q = keys[state_digest]
        with_hash = {u:d for u,d in indexed.db.execute("SELECT unit,unit_digest FROM unit WHERE state=?",(state,))}
        # Map every candidate to its source ID. Public label groups alone need not contain it.
        rows = indexed.units(state)
        label = labels[q]
        ids = set().union(*(set(g["acceptable_evidence_ids"]) for g in label["required_evidence_groups"]),
                          *(set(a) for a in label["alternative_minimal_sets"]),set(predictions[q]["matched_unary"]),set(predictions[q]["dense_state"]))
        id_map = {hashed(uid):uid for uid in ids}
        @lru_cache(None)
        def ideal_k(k):
            gs = label.get("required_evidence_groups", [])
            return original_ideal(gs, [float(g.get("necessity_weight",1.0)) for g in gs], k)
        native.ideal_group_dcg = lambda groups, weights, k: ideal_k(k)
        def assessed(top):
            # Non-gold IDs outside published top-k can be passed as unique non-member tokens.
            actual = [id_map.get(with_hash[j],"outside-label:"+with_hash[j]) for j in top]
            scores = []
            for k in (5,8):
                val = grader.evaluate(state,top,k)["complete"]
                assert native.score_prediction(actual,label,k)[f"mss_complete@{k}"] == val
                checks["native_metric_comparisons"] += 1
                scores.append(val)
            return scores
        base, bge = indexed.top(state), indexed.top(state,mode="bge")
        assert base == fresh.top(state,mode="fresh")
        for method, seq in (("matched_unary",base),("dense_state",bge)):
            assert [with_hash[u] for u in seq] == [hashed(x) for x in predictions[q][method]]
            checks["frozen_rank_lists"] += 1
        base_mss, bge_mss = assessed(base), assessed(bge)
        baselines[state] = dict(units=len(rows), seen=sum(r["seen"] for r in rows),ret=base,bge=bge,mss=base_mss,bge_mss=bge_mss)
        for old in (0,1):
            unit = next((r["unit"] for r in rows if r["seen"]==old),None)
            if unit is None:
                continue
            timings = {"indexed":[],"fresh":[]}
            calls = {"indexed":[],"fresh":[]}
            for replica in range(6):
                runs = [("indexed",indexed,False),("fresh",fresh,True)]
                if (ix+replica+old)%2:
                    runs.reverse()
                answers = {}
                for name,engine,full in runs:
                    count = engine.model.calls
                    t0 = perf_counter_ns()
                    answers[name] = engine.set_seen(state,unit,1-old,fresh=full)
                    elapsed = perf_counter_ns()-t0
                    count = engine.model.calls-count
                    assert count == (len(rows) if full else 1)
                    if replica:
                        timings[name].append(elapsed)
                        calls[name].append(count)
                assert answers["indexed"] == answers["fresh"]
                changed = answers["indexed"]
                if replica == 0:
                    assert indexed.top(state,mode="bge") == bge
                    assert not indexed.db.execute(
                        "SELECT 1 FROM unit WHERE state=? AND score!=tree_score(features,seen) LIMIT 1",(state,)).fetchone()
                    after_mss = assessed(changed)
                assert indexed.set_seen(state,unit,old) == base
                assert fresh.set_seen(state,unit,old,fresh=True) == base
            records.append(dict(state=state,unit=unit,previous=old,updated=1-old,after=changed,
                                mss=after_mss,ns=timings,ensemble_calls=calls))
    native.ideal_group_dcg = original_ideal
    checks["indexed_full_flip_replica_pairs"] = 6*len(records)
    stats_all = {name:stats([x for row in records for x in row["ns"][name]]) for name in ("indexed","fresh")}
    diffs = Counter()
    for r in records:
        base = baselines[r["state"]]
        for j,k in enumerate((5,8)):
            diffs[f"order_{k}"] += r["after"][:k] != base["ret"][:k]
            diffs[f"set_{k}"] += set(r["after"][:k]) != set(base["ret"][:k])
            diffs[f"mss_gain_{k}"] += r["mss"][j] > base["mss"][j]
            diffs[f"mss_loss_{k}"] += r["mss"][j] < base["mss"][j]
    payload = json.dumps(dict(baselines=baselines,flip_records=records),sort_keys=True,separators=(",",":")).encode()
    (D/"replicas.json.gz").write_bytes(gzip.compress(payload,mtime=0))
    out = dict(states=len(baselines), flips=len(records),checks=checks,differences=diffs, timings=stats_all,
               baseline_mss={a:[sum(r[a][j] for r in baselines.values()) for j in (0,1)] for a in ("mss","bge_mss")},
               calls={name:sum(sum(r["ensemble_calls"][name]) for r in records) for name in stats_all},
               median_speedup=stats_all["fresh"]["median_us"]/stats_all["indexed"]["median_us"],load_ms=load_ms,
               units=sum(r["units"] for r in baselines.values()), repo_count=indexed.db.execute("SELECT count(DISTINCT repo_digest) FROM state").fetchone()[0],
               sql_plans=plans,sqlite=sqlite3.sqlite_version,python=platform.python_version(),os=platform.platform(),
               baseline_sha=seal["predictions"],native_sha=sha(UP/"src/serbench/_reference_scorer.py"),replicas_sha=sha(D/"replicas.json.gz"))
    (D/"results.json").write_bytes((json.dumps(out,sort_keys=True,indent=2)+"\n").encode())
    print(json.dumps(out,ensure_ascii=True))


if __name__ == "__main__":
    main()
