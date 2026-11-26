"""Exact paired evaluation of observable graph-reading policies on a frozen reader."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import sys

ROOT = Path(__file__).resolve().parent
R50 = ROOT.parents[1] / "graph_memory_round50"
PANELS = ("adaptive_address", "gate_confirmation", "transfer", "routing")
INPUTS = ("contexts.json.gz", "orders.json.gz", "outcomes.json.gz", "prompts.json.gz",
          "answers.json.gz", "answer-seal.json", "threshold-seal.json", "input-seal.json")

def read(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf8"))

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def source(panel, names=INPUTS):
    new={"transfer":"f9012fbbd9d29c8db214e5e80ac56338f99f1c06ae66fc0062d84fc29c63e449",
         "routing":"5f9bae02d47e992556b273ca6c51e36408bbf40bd70d147356eb776d379e52e4"}
    root = ROOT.parent / panel if panel in new else R50 / panel
    if panel in new:
        receipt = root / "SHA256.json"
        assert digest(receipt.read_bytes()) == new[panel]
        files = read(receipt)
    else:
        files = read(root / "manifest.json")["files"]
    for name in names:
        if digest((root / name).read_bytes()) != files[name]:
            raise ValueError(f"Archived input {panel}/{name} changed")
    return {name.split(".")[0]: read(root/name) for name in names}

def snapshot(seal):
    keys = ["model", "engine", "inference", "client", "props"]
    return digest(json.dumps([seal[k] for k in keys], sort_keys=True).encode())

def build(db):
    db.executescript("""
        CREATE TABLE panel(name TEXT PRIMARY KEY, snapshot TEXT, threshold REAL);
        CREATE TABLE prices(snapshot TEXT, prompt TEXT, input_tokens INT, output_tokens INT,
                            PRIMARY KEY(snapshot,prompt)) WITHOUT ROWID;
        CREATE TABLE routes(panel TEXT, question TEXT, cluster TEXT, gap REAL,
                            dense TEXT, linked TEXT, PRIMARY KEY(panel,question)) WITHOUT ROWID;
        CREATE TABLE observed(panel TEXT, question TEXT, prompt TEXT, em REAL, f1 REAL,
                              PRIMARY KEY(panel,question,prompt)) WITHOUT ROWID;
        CREATE INDEX crossing ON routes(panel,gap) WHERE gap IS NOT NULL;
    """)
    for panel in PANELS:
        data = source(panel)
        snap = snapshot(data["answer-seal"])
        db.execute("INSERT INTO panel VALUES(?,?,?)", (panel,snap,data["threshold-seal"]["primary"]))
        for key, tokens in data["prompts"].items():
            if digest(struct.pack(f"<{len(tokens)}I", *tokens)) != key:
                raise ValueError("Invalid prompt hash")
            price = (snap, key, len(tokens), data["answers"][key]["tokens"])
            db.execute("INSERT OR IGNORE INTO prices VALUES(?,?,?,?)", price)
            assert db.execute("SELECT * FROM prices WHERE snapshot=? AND prompt=?",price[:2]).fetchone() == price
        for q, row in sorted(data["contexts"].items()):
            order = data["orders"][q]
            best = order["order"][0]
            linked = next((k for k in order["order"] if k in order["edges"]), best)
            gap = None if best == linked else order["scores"][str(best)] - order["scores"][str(linked)]
            assert gap is None or 0 <= gap <= 2
            refs = row["refs"]
            assert (refs["dense"][0],refs["linked_dense"][0]) == (best, linked)
            db.execute("INSERT INTO routes VALUES(?,?,?,?,?,?)",
                       (panel,q,row["cluster"],gap,refs["dense"][1],refs["linked_dense"][1]))
            for arm in ("dense", "linked_dense"):
                prompt = refs[arm][1]
                em, f1 = data["outcomes"][q]["arms"][arm][:2]
                obs = (panel,q,prompt,em,f1)
                db.execute("INSERT OR IGNORE INTO observed VALUES(?,?,?,?,?)", obs)
                assert db.execute("SELECT * FROM observed WHERE panel=? AND question=? AND prompt=?",obs[:3]).fetchone()==obs
    db.commit()
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)

def threshold(label, frozen):
    if label == "dense":
        return -1.0
    if label == "always":
        return 2.0
    if label == "registered":
        return frozen
    number = float(label)
    if not math.isfinite(number) or not 0 <= number <= 2:
        raise ValueError("A numeric threshold must be within [0, 2]")
    return number

def assignment(rows, cutoff):
    return {q: linked if gap is not None and gap <= cutoff else dense
            for q, gap, dense, linked in rows}

def crossing_plan(db, panel, old, new):
    low, high = sorted((old,new))
    hits = db.execute("""SELECT question,dense,linked FROM routes
                         WHERE panel=? AND gap>? AND gap<=? AND dense<>linked""", (panel,low,high))
    return {q: (a,b) if old<=new else (b,a) for q,a,b in hits}

def cost(keys, prices):
    return {"calls": len(keys), "input_tokens": sum(prices[k][0] for k in keys),
            "output_tokens": sum(prices[k][1] for k in keys)}

def evaluate(db, panel, start, end):
    snap, frozen = db.execute("SELECT snapshot,threshold FROM panel WHERE name=?", (panel,)).fetchone()
    old, new = threshold(start,frozen), threshold(end,frozen)
    rows = list(db.execute("SELECT question,gap,dense,linked FROM routes WHERE panel=?",(panel,)))
    left, right = assignment(rows,old), assignment(rows,new)
    plan = crossing_plan(db,panel,old,new)
    assert plan == {q:(a,right[q]) for q,a in left.items() if a!=right[q]}
    leftkeys, rightkeys = set(left.values()), set(right.values())
    keys = {key for pair in plan.values() for key in pair}
    prices = {k:(i,o) for k,i,o in db.execute("SELECT prompt,input_tokens,output_tokens FROM prices WHERE snapshot=?", (snap,))}
    # These rows represent the reader contract. Access only keys demanded by the plan.
    deltas = []
    for q,(a,b) in sorted(plan.items()):
        scores = [db.execute("SELECT em,f1 FROM observed WHERE panel=? AND question=? AND prompt=?",
                             (panel,q,k)).fetchone() for k in (a,b)]
        deltas.append([q, a, b, scores[1][0]-scores[0][0],scores[1][1]-scores[0][1]])
    n = len(rows)
    return dict(panel=panel,start=start,end=end,n=n,changed_input=len(plan),
                cold_memoized=cost(leftkeys|rightkeys,prices),cold_delta=cost(keys,prices),
                warm_new_calls=cost(rightkeys-leftkeys,prices),absolute_start=cost(leftkeys,prices),
                zero_omitted=n-len(deltas),delta_em_pp=100*math.fsum(r[3] for r in deltas)/n,
                delta_f1_pp=100*math.fsum(r[4] for r in deltas)/n,
                wins=sum(r[4]>0 for r in deltas),losses=sum(r[4]<0 for r in deltas)), deltas

def run(dest):
    dest.mkdir(exist_ok=True, parents=True)
    db = sqlite3.connect(":memory:")
    build(db)
    out = {"sqlite":sqlite3.sqlite_version, "python":sys.version.split()[0], "panels":{}}
    for panel in PANELS:
        groups = {}
        witnesses = {}
        for a,b in (("dense","registered"), ("dense","always"), ("always","registered")):
            summary, records = evaluate(db,panel,a,b)
            groups[a+"-to-"+b] = summary
            witnesses[a+"-to-"+b] = records
        out["panels"][panel]=groups
        with (dest/(panel+"-witnesses.json.gz")).open("wb") as f:
            f.write(gzip.compress(json.dumps(witnesses,separators=(",",":")).encode(),mtime=0))
    out["query_plan"] = list(db.execute("EXPLAIN QUERY PLAN SELECT question,dense,linked FROM routes WHERE panel=? AND gap>? AND gap<=? AND dense<>linked",(PANELS[1],0,0.1)))
    dump(dest/"results.json", out)
    db.close()
    return out

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--output",type=Path)
    arg.add_argument("--panel",choices=PANELS,default=PANELS[1])
    arg.add_argument("--start",default="dense")
    arg.add_argument("--end",default="registered")
    args=arg.parse_args()
    if args.output:
        run(args.output)
    else:
        with sqlite3.connect(":memory:") as conn:
            build(conn)
            print(json.dumps(evaluate(conn,args.panel,args.start,args.end)[0],indent=2))

