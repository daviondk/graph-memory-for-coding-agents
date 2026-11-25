"""Validate the lossless operator against the frozen official test projection."""
import collections
import gzip
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

for var in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[var] = "1"
from operators import Packed, table, flat_stats, packed_stats, rank_strength, features_in_rank_order
import numpy as np

D = Path(__file__).resolve().parent
BASE = D.parents[1] / "graph_memory_round20/typed_reader"
spec = importlib.util.spec_from_file_location("typed_r20_reference", BASE/"study.py")
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)
CACHE = Path(os.environ.get("FACTORIZED_DB_ROOT", "D:/CodexResearch/x20-factorized-provenance"))
CACHE.mkdir(exist_ok=True, parents=True)
SCHEMA = {
    "flat": ["CREATE TABLE node(t INTEGER,n INTEGER,PRIMARY KEY(t,n)) WITHOUT ROWID",
             "CREATE TABLE edge(t INTEGER,a INTEGER,b INTEGER,k INTEGER,PRIMARY KEY(t,a,b,k)) WITHOUT ROWID"],
    "packed": ["CREATE TABLE node(t INTEGER,n INTEGER,g INTEGER NOT NULL,PRIMARY KEY(t,n)) WITHOUT ROWID",
               "CREATE TABLE adjacent(t INTEGER,a INTEGER,b INTEGER,PRIMARY KEY(t,a,b)) WITHOUT ROWID",
               "CREATE TABLE link(t INTEGER,a INTEGER,b INTEGER,k INTEGER,PRIMARY KEY(t,a,b,k)) WITHOUT ROWID"],
}


def save(path, data):
    raw = (json.dumps(data, ensure_ascii=False, separators=(",",":"), sort_keys=True, allow_nan=False)+"\n").encode()
    if path.suffix == ".gz":
        raw = gzip.compress(raw, compresslevel=5, mtime=0)
    tmp = path.with_suffix(path.suffix+".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def geometry(record):
    g = ref.ProvenanceGraph.model_validate(record["g"])
    ids = {n:i for i,n in enumerate(sorted(v.node_id for v in g.nodes
           if v.kind in {ref.ARGUMENT_CHUNK_NODE,ref.OUTPUT_CHUNK_NODE}))}
    member = {}
    adjacent, links = set(), set()
    for edge in g.edges:
        a,b = edge.source, edge.target
        if edge.relation in {ref.HAS_ARGUMENT_EDGE,ref.HAS_CONTENT_EDGE}:
            if b in ids:
                assert b not in member or member[b] == a
                member[b] = a
        elif edge.relation == ref.NEXT_CHUNK_EDGE and a in ids and b in ids and a != b:
            adjacent.add((ids[a],ids[b]))
    assert set(member) == set(ids)
    groups = {g:i for i,g in enumerate(sorted(set(member.values())))}
    def link(a,b,typ):
        if a in groups and b in groups:
            assert a != b, "a within-event product needs diagonal correction"
            links.add((groups[a],groups[b],typ))
    for e in g.edges:
        if e.relation == ref.RETURNS_EDGE:
            link(e.source,e.target,1)
    for dep in ref.logical_output_dependencies(g):
        k = {ref.FEEDS_EDGE:2,ref.RESOURCE_FLOW_RELATION:3}[dep.relation]
        link(dep.source_output_id,dep.target_output_id,k)
    membership = np.array([groups[member[n]] for n in ids], dtype=np.int64)
    return ids, Packed(membership,table(sorted(adjacent),2),table(sorted(links),3))


def make_db(kind):
    target = CACHE/(kind+".building.sqlite")
    if target.exists():
        raise FileExistsError(f"Preserve or move incomplete build before retrying: {target}")
    db = sqlite3.connect(target)
    for sql in SCHEMA[kind]:
        db.execute(sql)
    return db


def query_panel():
    n = []
    for i in range(8):
        n.extend(ref.read(BASE/f"test-graphs-{i}.json.gz"))
    tids = sorted(r["t"] for r in n)
    assert len(set(tids)) == len(tids) == 1207
    chosen = sorted(tids,key=lambda t:hashlib.sha256(("factor-store-v1"+t).encode()).digest())[:128]
    return tids,set(chosen)


def main():
    tids,panel = query_panel()
    index = ref.graph_index()
    weights = ref.read(BASE/"weights.json")["typed"]
    inputseal = ref.read(BASE/"prediction-plan.json")
    seal = ref.read(BASE/"forecast-seal.json")
    assert ref.sha(BASE/"weights.json") == ref.read(BASE/"fit-seal.json")["weights"]
    dbs = {k:make_db(k) for k in SCHEMA}
    systems, per_query, timings, samples = [], [], {}, []
    test_id = {t:i for i,t in enumerate(tids)}
    for shard in range(8):
        filename = f"forecasts-main-{shard}.json.gz"
        assert ref.sha(ref.TR/filename) == inputseal["test"][filename]
        previous = BASE/f"forecast-{shard}.json.gz"
        assert ref.sha(previous) == seal["forecasts"][previous.name]
        choices = {r["q"]:r for r in ref.read(previous)}
        by = collections.defaultdict(list)
        for row in ref.read(ref.TR/filename):
            by[row["t"]].append(row)
        for t,qs in sorted(by.items()):
            tid = test_id[t]
            source,h = index[t]
            assert ref.sha(source) == h
            ids,g = geometry(ref.read(source))
            native = ref.project(t,index)
            assert ids == native[0]
            arcs = sorted((int(a),int(b),typ) for typ in range(4) for a,b in native[1][2*typ].T)
            members = collections.defaultdict(list)
            for n,group in enumerate(g.membership):
                members[int(group)].append(n)
            reconstructed = {(int(a),int(b),0) for a,b in g.adjacent}
            for a,b,k in g.links:
                reconstructed.update((u,v,int(k)) for u in members[a] for v in members[b])
            assert len(arcs) == len(reconstructed) and set(arcs) == reconstructed,t
            edge = table(arcs,3)
            for dbkind,db in dbs.items():
                with db:
                    if dbkind == "packed":
                        db.executemany("INSERT INTO node VALUES(?,?,?)",((tid,j,int(v)) for j,v in enumerate(g.membership)))
                        db.executemany("INSERT INTO adjacent VALUES(?,?,?)",((tid,int(a),int(b)) for a,b in g.adjacent))
                        db.executemany("INSERT INTO link VALUES(?,?,?,?)",((tid,int(a),int(b),int(k)) for a,b,k in g.links))
                    else:
                        db.executemany("INSERT INTO node VALUES(?,?)",((tid,j) for j in range(len(ids))))
                        db.executemany("INSERT INTO edge VALUES(?,?,?,?)",((tid,*r) for r in arcs))
            systems.append(dict(t=t,tid=tid,source_sha256=h,n=len(ids),groups=len(members),edges=len(arcs),
                                adjacent=len(g.adjacent),links=len(g.links),q=len(qs)))
            for index_q,r in enumerate(sorted(qs,key=lambda x:x["q"])):
                rr = r["rr"]
                order = np.array([ids[v["node_id"]] for v in rr])
                assert set(order) == set(range(len(ids)))
                strength = rank_strength(order)
                old = flat_stats(len(ids),edge,strength)
                new = packed_stats(g,strength)
                error = float(np.max(abs(new-old)))
                assert error < 1e-10
                x = features_in_rank_order(order,new)
                native_features = ref.project_rows(rr,native)["typed"]
                assert np.max(abs(x-native_features)) < 1e-10
                ranking = np.argsort(-(x@weights["w"]+weights["bias"]),kind="stable")
                cost = [v["token_count"] for v in rr]
                selected = {pol:ref.pack(ranking,cost,pol=="skip") for pol in ("prefix","skip")}
                refsel = choices[r["q"]]["selection"]["typed"]
                same = {pol:selected[pol]==refsel[pol] for pol in selected}
                per_query.append(dict(t=t,q=r["q"],n=len(ids),error=error,match=same,
                                      discrepancies={k:selected[k] for k in same if not same[k]}))
                if t in panel and index_q==0:
                    timings[t]=dict(tid=tid,q=r["q"],order=order.tolist())
        print("validated shard",shard,len(per_query),len(systems),flush=True)
    assert len(per_query)==len({r["q"] for r in per_query})==2000 and len(systems)==1207 and len(timings)==128
    save(D/"by-trajectory.json.gz",systems);save(D/"by-query.json.gz",per_query)
    save(D/"timing-panel.json.gz",timings)
    files = {}
    for kind,db in dbs.items():
        db.execute("VACUUM")
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        db.close()
        src=CACHE/(kind+".building.sqlite");dst=CACHE/(kind+".sqlite")
        os.replace(src,dst)
        files[kind]={"bytes":dst.stat().st_size,"sha256":ref.sha(dst)}
    save(D/"projection-lock.json",{"db":files,"query":ref.sha(D/"by-query.json.gz"),
         "history":ref.sha(D/"by-trajectory.json.gz"),"timing":ref.sha(D/"timing-panel.json.gz"),
         "reference":ref.sha(BASE/"study.py"),"frozen_weights":ref.sha(BASE/"weights.json"),
         "protocol":ref.sha(D/"PROTOCOL_RU.md"),"code":ref.sha(D/"study.py"),"operators":ref.sha(D/"operators.py"),
         "inputs":ref.sha(BASE/"prediction-plan.json"),"native_forecasts":ref.sha(BASE/"forecast-seal.json"),
         "queries":len(per_query),"trajectories":len(systems),"sqlite":sqlite3.sqlite_version})
    print(files,flush=True)


if __name__ == "__main__":
    main()
