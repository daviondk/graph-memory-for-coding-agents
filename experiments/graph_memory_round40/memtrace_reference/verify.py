"""Offline event-by-event verifier. No external MemTrace, network, GPU or data required."""
from collections import defaultdict
from project import D, digest, read


def main():
    seal=read(D/"input-seal.json")
    for name,sha in seal["files"].items(): assert digest(D/name)==sha, name
    records=read(D/"cases.json.gz");ref=read(D/"comparison-reference.json.gz")
    native=read(D/"native-projections.json.gz");predicate=read(D/"predicate.json.gz")
    assert set(records)==set(ref)==set(predicate) and len(records)==2696
    run=read(D/"native-run.json");assert run["projected_sha256"]==digest(D/"native-projections.json.gz")
    assert run["replay_sha256"]==digest(D/"replay.py") and run["predicate_sha256"]==digest(D/"predicate.json.gz")
    dbkey=set(native);panel=read(D/"panel.json");pilot=read(D/"pilot-decision.json")
    assert dbkey==(set(records) if pilot["qualified"] else set(panel["pilot"]))
    assert len(panel["pilot"])==64 and set(panel["pilot"]).isdisjoint(panel["other"])
    assert set(panel["pilot"])|set(panel["other"])==set(records)
    fixture=read(D/"fixtures.json");assert len(fixture["tests_passed"])==2 and fixture["symbol"]["closed_slots"]==[0] and fixture["file"]["closed_slots"]==[0,1,3]
    tab=read(D/"results.json")
    assert tab["native_seal"]==digest(D/"native-run.json") and tab["reference"]==digest(D/"comparison-reference.json.gz")
    groups=defaultdict(list)
    for k,row in records.items():
        expect=sorted(b["slot"] for b in row["chosen"] if b["path"]==row["changed"])
        assert predicate[k]==expect and ref[k]["file_reuse"]==int(not expect)
        if k in dbkey:
            db=native[k];assert db["closed_slots"]==expect and db["edge_count"]==len(expect)
            assert db["closed_bytes"]==sum(b["bytes"] for b in row["chosen"] if b["slot"] in expect)
            assert db["blocks"]==len(row["chosen"]) and db["old_active"]==len(row["chosen"])-len(expect)
            groups["all"].append(k);groups[row["group"]].append(k)
    for grp,keys in groups.items():
        z=tab["groups"][grp]
        assert z["n"]==len(keys) and z["issues"]==len({records[k]["issue"] for k in keys})
        assert z["db_active_packets"]==sum(not native[k]["closed_slots"] for k in keys)
        assert z["strict_range_packets"]==sum(ref[k]["strict_range"] for k in keys)
        assert z["closed_block_occurrences"]==sum(len(native[k]["closed_slots"]) for k in keys)
        assert z["closed_bytes"]==sum(native[k]["closed_bytes"] for k in keys)
        assert z["old_active"]==sum(native[k]["old_active"] for k in keys)
    if (D/"manifest.json").exists():
        for fn,sha in read(D/"manifest.json")["files"].items():assert digest(D/fn)==sha,fn
    print(f"Verified {len(native)} SQLite edit results, {len(records)} native entity predictions, two original unit tests, and primary aggregate counts.")


if __name__=="__main__":
    main()

