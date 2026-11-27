"""Charge actual natural-length SQLite writes/preloads with unchanged future-query traces."""
import argparse
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import zlib

from run_transfer import ARMS, GROUPS, HERE, WORKLOADS, digest, load, save, source
from audit import chosen as independent_selection
from bench_restart import panels
from checkpoint import CRC, Demand, Reader, Pinned, make_snapshot, persist, unpack_snapshot


def prefix(stream):
    ids = {}
    events = []
    for sha,raw in stream:
        if len(raw)>64:
            continue
        codes = tuple(ids.setdefault(p,len(ids)) for p in raw)
        if len(codes)>=2:
            events.append((sha,codes))
    return events[:len(events)//2]


def logical_read_inputs(reader):
    return (reader.pinned, reader.pinned_for, reader.complete, reader.hot.live,
            reader.hot.lost_shared, reader.fence)


def restore(path, blob):
    writer = Pinned(path,False)
    assert writer.db.execute("PRAGMA synchronous").fetchone()==(2,)
    persist(writer.db,blob)
    sql_bytes = writer.db.execute("SELECT length(v) FROM snapshot WHERE k=1").fetchone()[0]
    assert sql_bytes==len(blob)
    writer.close()
    reader = Pinned(path,True)
    assert reader.loaded_bytes==sql_bytes and not reader.rejected
    return reader, sql_bytes


def measure_snapshot(path, stream):
    past = prefix(stream)
    bodies = [ids for sha,ids in past]
    writer = Reader(path,"shared",True)
    demand = Demand()
    for j,(sha,ids) in enumerate(past):
        assert writer.append(j,sha,ids)
        demand.append(ids)
    live = dict(writer.hot.live)
    writer.close()
    cold = Pinned(path,False)
    assert not cold.pinned and not cold.loaded_bytes and not cold.receipt_bytes
    cold.close()
    stats = {"cold":dict(selected=0,all_live=len(live),written=0,loaded=0,receipt=0,old_size=0)}
    for mode,(rule,cap) in ARMS.items():
        if mode=="cold":
            continue
        padded,n,useful = make_snapshot(live,len(past),past[-1][0],rule,cap,demand)
        index,bytes_used,original = independent_selection(bodies,cap,rule)
        assert (n,useful,len(padded))==(len(index),bytes_used,original)
        # Same envelope and body; remove only the no-op padding and refresh CRC.
        compact_message = padded[:useful-CRC.size]
        blob = compact_message + CRC.pack(zlib.crc32(compact_message))
        expected = {j:bodies[j] for j in index}
        assert {j:tuple(ids) for j,ids in unpack_snapshot(blob,len(past),bytes.fromhex(past[-1][0])).items()}==expected
        old,w = restore(path,padded)
        old_inputs = logical_read_inputs(old)
        assert old.receipt_bytes==20 and w==len(padded)
        old.close()
        new,w = restore(path,blob)
        assert old_inputs==logical_read_inputs(new)
        assert {j:tuple(ids) for j,ids in new.pinned.items()}==expected
        stats[mode] = dict(selected=n,all_live=len(live),written=w,loaded=new.loaded_bytes,
                           receipt=new.receipt_bytes,old_size=len(padded))
        assert w==useful and new.receipt_bytes==20
        new.close()
    return stats


def read_costs():
    original = load(HERE.parent/"restart"/"runs.json.gz")["runs"]
    external = load(HERE/"runs.json.gz")["projects"]
    costs = defaultdict(dict)
    for r in original:
        if r["rep"]!=0:continue
        k=("original-"+r["panel"],r["project"])
        posts = [q for q in r["queries"] if q[0]]
        costs[k][r["method"]] = (sum(q[4] for q in posts),sum(q[6] for q in posts),r["stats"]["snapshot_write"])
    for k,v in external.items():
        g,p=k.split("/",1)
        for workload in WORKLOADS:
            for m,arm in v["workloads"][workload]["arms"].items():
                a=arm["summary"]
                costs[(g+"-"+workload,p)][m] = (a["posting_bytes"],a["body_bytes"],a["written"])
    return costs


def produce():
    costs = read_costs()
    streams = []
    for group,data in panels().items():
        if group not in ("B","long"):continue
        for p,rows in data.items():
            streams.append((p,["original-"+group],rows))
    for g in GROUPS:
        data,_ = source(g)
        streams.extend((p,[g+"-"+w for w in WORKLOADS],rows) for p,rows in data.items())
    assert len(streams)==len({p for p,_,_ in streams})==21
    bases = {}
    cases = defaultdict(dict)
    with TemporaryDirectory(dir=HERE,prefix="natural-") as td:
        for p,groups,rows in streams:
            path=Path(td)/"one.sqlite"
            paid=measure_snapshot(path,rows)
            path.unlink()
            assert not list(Path(td).iterdir())
            bases[p]=paid
            for g in groups:
                case={}
                for m,o in paid.items():
                    pb,bb,old=costs[(g,p)][m]
                    assert old==o["old_size"]
                    case[m]=dict(paid=o["written"]+o["loaded"]+o["receipt"],postings=pb,bodies=bb,
                                 charged=o["written"]+o["loaded"]+o["receipt"]+pb+bb,
                                 old_charged=2*old+o["receipt"]+pb+bb)
                cases[g][p]=case
    aggregate={}
    all_cases=dict(cases)
    for w in WORKLOADS:
        all_cases["external-"+w]={k:v for g in GROUPS for k,v in cases[g+"-"+w].items()}
    for g,projects in all_cases.items():
        summary={}
        for m in ARMS:
            summary[m]=dict(charged=sum(c[m]["charged"] for c in projects.values()),
                            old_charged=sum(c[m]["old_charged"] for c in projects.values()),
                            all_live=sum(bases[p][m]["selected"]==bases[p][m]["all_live"] for p in projects),
                            projects=len(projects))
        aggregate[g]=summary
    return dict(protocol=digest(HERE/"NO_PADDING_PROTOCOL_RU.md",True),
                snapshots=bases,projects=cases,aggregate=aggregate)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    result=produce()
    if verify:assert result==load(HERE/"no-padding.json")
    else:save(HERE/"no-padding.json",result)
    print("Verified actual natural-length SQLite reloads for",len(result["snapshots"]),"histories.")


if __name__=="__main__":
    main()
