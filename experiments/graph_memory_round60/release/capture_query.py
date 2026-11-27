"""Export the earliest dense Tablib query with two certified missing IDs and a quiet guard miss."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
sys.path.insert(0, str(ROUND/"coverage"))
from run_coverage import BlockStore, Coverage, Hot, NEW_SHA, load, possible_losses, prepare, varints
from coverage import EVENT, EXCEPTION, POST

PROJECT = "jazzband/tablib"


def capture(destination):
    source = ROUND/"panel/events.json.gz"
    assert sha256(source.read_bytes()).hexdigest() == NEW_SHA
    history = load(source)[PROJECT]
    records = load(ROUND/"coverage/runs.json.gz")["cases"]["new/B/"+PROJECT]["logs"]
    wanted = next(i for i,r in enumerate(records)
                  if r["arms"]["1024/notify"].get("certified_multiple") and r["arms"]["1024/lazy"].get("guard_fallback"))
    ops, _ = prepare(history, "B")
    names = {}
    for _, members in history:
        if len(members) <= 64:
            for m in members:
                names.setdefault(m, len(names))
    paths = {i: path for path, i in names.items()}
    fence = sum(op[0] == "w" for op in ops)//2
    with TemporaryDirectory(dir=destination) as temp:
        sqlite = Path(temp)/"source.sqlite"
        with closing(BlockStore(sqlite, "filelist", True)) as db:
            hot = Hot()
            readers = {}
            index = 0
            for op in ops:
                if not readers and db.next_id == fence:
                    readers = {m:Coverage(db, hot, 1024, m == "notify") for m in ("notify", "quiet")}
                if op[0] == "w":
                    _, j, rev, files = op
                    assert db.append(j, rev, files)
                    if readers:
                        before = possible_losses(hot, files)
                        hot.append(j, files)
                        lost = [(k, before[k]) for k in sorted(before) if k not in hot.live]
                        for r in readers.values():
                            r.after_committed(j, files, lost)
                elif readers:
                    _, f, tie, prior, expected = op
                    if index == wanted:
                        baseline = records[index]
                        assert (baseline["anchor"], baseline["prefix"]) == (f, db.next_id)
                        states = {}
                        for label, r in readers.items():
                            packet = r.cache.items[(POST, f)]
                            assert packet[0] == EXCEPTION
                            states[label] = dict(packet=packet.hex(), resident_lru_bytes=r.cache.size,
                               event_blobs={j:blob.hex() for (kind,j),blob in r.cache.items.items() if kind==EVENT})
                        hot_blobs = {j:varints(hot.live[j]).hex() for j in hot.incident.get(f, ())}
                        query = dict(project=PROJECT, source_archive_sha256=NEW_SHA, t=baseline["t"],
                                     target_commit=baseline["sha"], archival_head=history[-1][0],
                                     query=index+1, fence=fence, prefix=db.next_id, anchor=f,
                                     paths={k:paths[k] for k in tie}, tie=tie, prior=prior, expected=expected,
                                     hot_incident=hot_blobs, states=states)
                    for label,r in readers.items():
                        ranking, counters = r.read(f, tie, prior)
                        assert ranking == expected
                        known = records[index]["arms"]["1024/"+("lazy" if label=="quiet" else label)]
                        assert {k:v for k,v in known.items() if k!="resident"} == dict(counters)
                        assert known["resident"] == r.cache.size
                        if index == wanted:
                            states[label]["recorded_reads"] = {k:counters[k] for k in ("posting_calls","posting_bytes","body_calls","body_bytes")}
                    if index == wanted:
                        break
                    index += 1
            else:
                raise ValueError("selected query not found")
            assert db.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0,0,0)
        shutil.copyfile(sqlite, destination/"source.sqlite")
    (destination/"query.json").write_bytes((json.dumps(query,sort_keys=True,separators=(",",":"))+"\n").encode())
    return query


if __name__ == "__main__":
    q = capture(HERE)
    print(q["project"], q["query"], q["paths"][q["anchor"]], q["states"]["notify"]["recorded_reads"])
