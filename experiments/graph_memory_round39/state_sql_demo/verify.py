"""Standard-library verification of the portable archive, SQLite indexes and all toggles."""
import gzip
import hashlib
import json
from statistics import median
from reader import D, Reader, Grader


def h(b):
    return hashlib.sha256(b).hexdigest()


def main():
    manifest = json.loads((D/"manifest.json").read_bytes())["files"]
    assert all(h((D/f).read_bytes())==v for f,v in manifest.items())
    summary = json.loads((D/"results.json").read_bytes())
    bundle = json.loads(gzip.decompress((D/"replicas.json.gz").read_bytes()))
    reader, grader = Reader(), Grader()
    assert reader.db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    assert grader.db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    assert all("grader" not in name for _,name,_ in reader.db.execute("PRAGMA database_list"))
    assert set(reader.states()) == set(bundle["baselines"])
    for state,base in bundle["baselines"].items():
        for mode, key, mss in (("indexed","ret","mss"),("fresh","ret","mss"),("bge","bge","bge_mss")):
            seq = reader.top(state,mode=mode)
            assert seq == base[key]
            assert [grader.evaluate(state,seq,k)["complete"] for k in (5,8)] == base[mss]
    flips = bundle["flip_records"]
    for r in flips:
        state = r["state"]
        assert reader.set_seen(state,r["unit"],r["updated"]) == r["after"]
        assert reader.top(state,mode="fresh") == r["after"]
        assert [grader.evaluate(state,r["after"],k)["complete"] for k in (5,8)] == r["mss"]
        assert reader.set_seen(state,r["unit"],r["previous"]) == bundle["baselines"][state]["ret"]
    for name in ("indexed","fresh"):
        ns = [v for record in flips for v in record["ns"][name]]
        assert len(ns) == summary["timings"][name]["n"]
        assert median(ns)/1000 == summary["timings"][name]["median_us"]
    previous = D.parent/"set_reader"/"predictions.json.gz"
    if previous.is_file():
        assert h(previous.read_bytes()) == summary["baseline_sha"]
        published = json.loads(gzip.decompress(previous.read_bytes()))
        for state_digest,state in reader.db.execute("SELECT state_digest,state FROM state"):
            key = next(q for q in published if h(q.encode()) == state_digest)
            units = dict(reader.db.execute("SELECT unit,unit_digest FROM unit WHERE state=?",(state,)))
            for method,index in (("matched_unary","ret"),("dense_state","bge")):
                assert [units[u] for u in bundle["baselines"][state][index]] == [h(e.encode()) for e in published[key][method]]
    print(len(manifest),"files,",len(reader.states()),"states,",len(flips),"reversible changes passed")


if __name__ == "__main__":
    main()
