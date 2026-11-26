"""Project public numeric features and graph edges. No archive instructions execute."""
from pathlib import Path
import gzip
import hashlib
import json
import sqlite3
import sys
import time
from reader import D, Ensemble

R = D.parent/"set_reader"
sys.path.insert(0,str(R))
import data


def write_json(name, value):
    (D/name).write_bytes((json.dumps(value, sort_keys=True, indent=2)+"\n").encode())


def main():
    protocol = data.sha(D/"PROTOCOL_RU.md")
    assert protocol == "cabb7cdce7ace5af78d19a81388954536cf21f57a45fb693e98d5cadeb7aa468"
    manifest = data.get(R/"manifest.json")["files"]
    for f in ("data.py","trees.json.gz","selection.json","seal.json","predictions.json.gz"):
        assert data.sha(R/f) == manifest[f]
    selection = data.get(R/"selection.json")
    assert selection["unary_weight"] == 1.0 and data.sha(R/"trees.json.gz") == selection["trees"]
    params = data.get(R/"trees.json.gz")["models"][0]
    (D/"model.json.gz").write_bytes(gzip.compress(json.dumps(params, separators=(",",":")).encode(),mtime=0))
    model = Ensemble(params)
    tic = time.perf_counter()
    all_states = data.inference()
    feature_seconds = time.perf_counter()-tic
    test = {q:r for q,r in all_states.items() if r["split"] == "test"}
    del all_states
    qmap = {q:f"s{j:03d}" for j,q in enumerate(sorted(test),1)}
    unit_ix = {q:{eid:i for i,eid in enumerate(r["ids"],1)} for q,r in test.items()}
    reader = sqlite3.connect(D/"reader.build.sqlite")
    grader = sqlite3.connect(D/"grader.build.sqlite")
    reader.executescript("""
      DROP TABLE IF EXISTS unit; DROP TABLE IF EXISTS state;
      CREATE TABLE state(state TEXT PRIMARY KEY, state_digest TEXT UNIQUE,repo_digest TEXT,task_digest TEXT) WITHOUT ROWID;
      CREATE TABLE unit(state TEXT,unit INTEGER,unit_digest TEXT,file TEXT,line_start INTEGER,line_end INTEGER,tokens INTEGER,
        base_seen INTEGER CHECK(base_seen IN (0,1)),seen INTEGER CHECK(seen IN (0,1)),
        bge_rank INTEGER, features BLOB,base_score REAL,score REAL,PRIMARY KEY(state,unit)) WITHOUT ROWID;
      """)
    grader.executescript("""
      DROP TABLE IF EXISTS evaluation_state; DROP TABLE IF EXISTS required;
      DROP TABLE IF EXISTS acceptable; DROP TABLE IF EXISTS alternative;
      CREATE TABLE evaluation_state(state TEXT PRIMARY KEY) WITHOUT ROWID;
      CREATE TABLE required(state TEXT,gid INTEGER,quota INTEGER,PRIMARY KEY(state,gid)) WITHOUT ROWID;
      CREATE TABLE acceptable(state TEXT,gid INTEGER,unit INTEGER,PRIMARY KEY(state,gid,unit)) WITHOUT ROWID;
      CREATE TABLE alternative(state TEXT,route INTEGER,unit INTEGER,PRIMARY KEY(state,route,unit)) WITHOUT ROWID;
      """)
    alias = lambda v: hashlib.sha256(v.encode()).hexdigest()
    begin = time.perf_counter()
    unit_count = 0
    for item in data.stream(data.PUB/"items.jsonl.gz"):
        q = item["state_id"]
        if q not in test:
            continue
        state, r = qmap[q], test[q]
        reader.execute("INSERT INTO state VALUES(?,?,?,?)", (state,alias(q),alias(r["repo"]),alias(r["task"])))
        candidates = {c["evidence_id"]:c for c in item["candidate_evidence"]}
        ranks = {int(i):j for j,i in enumerate(r["bge"],1)}
        for i, eid in enumerate(r["ids"]):
            c = candidates[eid]
            seen = int(c["observed_by_state"])
            assert r["x"][i,11] == seen and len(r["x"][i]) == params["width"]
            features = r["x"][i].astype("<f4").tobytes()
            score = model.value(features, seen)
            file = alias(r["repo"]+"\0"+c["source_path"])
            reader.execute("INSERT INTO unit VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (state,i+1,alias(eid),file,c.get("line_start"),c.get("line_end"),int(r["qw"][i]),
                 seen,seen,ranks[i],features,score,score))
            unit_count += 1
    reader.executescript("CREATE INDEX top_score ON unit(state,score DESC,unit); CREATE INDEX bge ON unit(state,bge_rank,unit);")
    reader.commit()
    reader.close()
    index_seconds = time.perf_counter()-begin
    for label in data.stream(data.PUB/"labels.jsonl.gz"):
        q = label["state_id"]
        if q not in test:
            continue
        state, ids = qmap[q], unit_ix[q]
        grader.execute("INSERT INTO evaluation_state VALUES(?)",(state,))
        for j,g in enumerate(label["required_evidence_groups"],1):
            grader.execute("INSERT INTO required VALUES(?,?,?)",(state,j,int(g["minimum_required"])))
            grader.executemany("INSERT INTO acceptable VALUES(?,?,?)",
                [(state,j,ids[e]) for e in sorted(set(g["acceptable_evidence_ids"])) if e in ids])
        for j,ls in enumerate(label["alternative_minimal_sets"],1):
            assert ls
            if all(e in ids for e in ls):
                grader.executemany("INSERT INTO alternative VALUES(?,?,?)",[(state,j,ids[e]) for e in sorted(set(ls))])
    grader.commit()
    grader.close()
    for name in ("reader","grader"):
        (D/(name+".build.sqlite")).replace(D/(name+".sqlite"))
    write_json("build.json",dict(states=len(test),units=unit_count,feature_seconds=feature_seconds,
        index_seconds=index_seconds,protocol=protocol,source_manifest=data.sha(R/"manifest.json"),
        seal=data.sha(R/"seal.json"),trees=selection["trees"],
        files={f:data.sha(D/f) for f in ("reader.sqlite","grader.sqlite","model.json.gz")}))
    print(len(test),unit_count,"feature seconds",feature_seconds,"index seconds",index_seconds)


if __name__ == "__main__":
    main()
