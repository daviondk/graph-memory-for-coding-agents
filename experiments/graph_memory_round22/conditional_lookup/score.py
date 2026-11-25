"""Open selected records and evaluate counterpart retrieval after the rankings are sealed."""
from collections import defaultdict
import sqlite3
import numpy as np
from prepare import ROOT, CACHE, SOURCE, SOURCE_SHA, read, dump, norm, sha

def grouped_interval(rows, first, second, seed=2219):
    groups = defaultdict(list)
    for row in rows:
        groups[row["family"]].append(row["methods"][first]["hit2"] - row["methods"][second]["hit2"])
    sizes = np.asarray([len(x) for x in groups.values()])
    sums = np.asarray([sum(x) for x in groups.values()])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(sizes), size=(10000, len(sizes)))
    diff = [d for group in groups.values() for d in group]
    return {"delta_pp": 100 * sum(diff) / len(diff), "n": len(rows), "families": len(sizes),
            "ci95_pp": (100 * np.quantile(sums[draws].sum(axis=1) / sizes[draws].sum(axis=1), [.025, .975])).tolist(),
            "wins": diff.count(1), "losses": diff.count(-1), "ties": diff.count(0)}
def main():
    lock = read(ROOT/"forecast-lock.json")
    assert sha((ROOT/"forecasts.json.gz").read_bytes()) == lock["forecast"]
    assert sha(SOURCE.read_bytes()) == SOURCE_SHA
    pos = read(SOURCE)["pos"]
    packets = {r["id"]: r for r in read(CACHE/"packets.json.gz")}
    forecasts = {r["id"]: r["picks"] for r in read(ROOT/"forecasts.json.gz")}
    assert set(forecasts) == set(packets)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE archive(doc TEXT, addr INTEGER, src TEXT NOT NULL, PRIMARY KEY(doc,addr)) WITHOUT ROWID")
    db.executemany("INSERT INTO archive VALUES(?,?,?)", [(doc, i, s) for doc, p in packets.items() for i, s in p["records"]])
    db.commit()
    db.execute("PRAGMA query_only=ON")
    rows = []
    for doc, row in sorted(pos.items()):
        refs = row.get("ref sentences", [])
        refs = [refs] if isinstance(refs, str) else refs
        refs = sorted({norm(s) for s in refs if norm(s)})
        packet = packets.get(doc, {"records": []})
        target = {i for i, s in packet["records"] if any(ref in s for ref in refs)}
        methods = {}
        for policy, ids in forecasts.get(doc, {}).items():
            assert len(ids) >= 2 and len(ids) == len(set(ids))
            returned = [db.execute("SELECT src FROM archive WHERE doc=? AND addr=?", (doc, i)).fetchone()[0] for i in ids]
            flags = [int(any(ref in text for ref in refs)) for text in returned]
            assert flags == [int(i in target) for i in ids]
            methods[policy] = {"hit1": int(flags[0]), "hit2": max(flags[:2]), "hit4": max(flags) if len(ids) == 4 else None,
                "opened": ids, "byte_cost2": sum(len(s.encode()) for s in returned[:2]), "digests": [sha(s.encode()) for s in returned]}
        rows.append({"id": doc, "family": doc.rsplit("_", 1)[0], "domain": row["doc_type"], "scope": "+".join(sorted(set(row["scope"]))) if isinstance(row["scope"], list) else row["scope"],
                     "labelled": bool(refs), "reachable": bool(target), "candidate_count": len(packet["records"]),
                     "target": sorted(target), "methods": methods})
    panel = [r for r in rows if r["reachable"]]
    assert panel
    def summarize(selected):
        return {p: {"hit1": sum(r["methods"][p]["hit1"] for r in selected),
                    "hit2": sum(r["methods"][p]["hit2"] for r in selected),
                    "hit4": sum(r["methods"][p]["hit4"] for r in selected) if p in ("hybrid","bm25","e5","local_fusion") else None,
                    "mean_bytes2": float(np.mean([r["methods"][p]["byte_cost2"] for r in selected]))}
                for p in selected[0]["methods"]}
    dump(ROOT/"outcomes.json.gz", rows)
    result = {"n": len(rows), "labelled": sum(r["labelled"] for r in rows), "panel": len(panel),
              "families": len({r["family"] for r in panel}), "sums": summarize(panel),
              "by_scope": {s: {"n": len(part), "sums": summarize(part)} for s in sorted({r["scope"] for r in panel})
                           if (part := [r for r in panel if r["scope"] == s])},
              "contrasts": {p + "/hybrid": grouped_interval(panel, p, "hybrid")
                            for p in ("signature","sham","neighbor","local_fusion","e5","bm25")},
              "forecast_lock": sha((ROOT/"forecast-lock.json").read_bytes()), "outcomes": sha((ROOT/"outcomes.json.gz").read_bytes())}
    dump(ROOT/"results.json", result)
    print(result["panel"], result["families"], result["sums"], result["contrasts"]["signature/hybrid"], flush=True)
if __name__ == "__main__":
    main()
