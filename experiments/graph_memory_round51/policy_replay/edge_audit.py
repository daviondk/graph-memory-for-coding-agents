"""Audit every single-edge toggle with full SQLite ranking before claiming packet reuse."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3
import rank_view

ROOT=Path(__file__).resolve().parent

def audit(db):
    db.row_factory=sqlite3.Row
    w=dict(db.execute("SELECT * FROM coef WHERE policy='graph'").fetchone())
    assert w["w4"]>0
    # The full SQL independently re-evaluates all rows with the bit inverted on exactly one tuple.
    sql=rank_view.RANK_SQL.replace("CASE WHEN c.cid=:suppress THEN 0 ELSE c.edge END",
                                   "CASE WHEN c.cid=:suppress THEN 1-c.edge ELSE c.edge END")
    counts={};examples=[]
    for panel in rank_view.NAMES:
        groups={"remove":Counter(),"add":Counter()}
        for (q,) in db.execute("SELECT q FROM question WHERE panel=? ORDER BY q",(panel,)):
            args=dict(panel=panel,q=q,method="graph",suppress=-1)
            order=list(db.execute(sql,args))
            observed={k:(f,p) for k,f,p in db.execute("SELECT cid,f1,prompt FROM response WHERE panel=? AND q=?",(panel,q))}
            head=order[0]["cid"]
            for item in order:
                kind="remove" if item["edge"] else "add"
                key=item["cid"]
                expected=db.execute(sql,dict(args,suppress=key)).fetchone()["cid"]
                winning=rank_view.certified(order,item,w,1-item["edge"])
                if expected!=winning:
                    raise AssertionError((q,key,winning,expected))
                g=groups[kind];g["toggles"]+=1
                if head==winning:
                    g["unchanged"]+=1
                    continue
                g["switched"]+=1
                known=winning in observed
                g["known" if known else "unknown"]+=1
                delta=None if not known else observed[winning][0]-observed[head][0]
                examples.append([panel,q,kind,key,head,winning,delta])
                if known:
                    g["gain" if delta>0 else "loss" if delta<0 else "equal_f1"]+=1
        counts[panel]=groups
    return counts,examples

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--record",action="store_true")
    args=parser.parse_args()
    with sqlite3.connect((ROOT/"rank.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True) as db:
        counts,records=audit(db)
    if args.record:
        (ROOT/"edge-results.json").write_text(json.dumps(counts,indent=2,sort_keys=True)+"\n",encoding="utf8")
        (ROOT/"edge-switches.json.gz").write_bytes(gzip.compress(json.dumps(records,separators=(",",":")).encode(),mtime=0))
    else:
        assert counts==json.loads((ROOT/"edge-results.json").read_bytes())
        assert records==json.loads(gzip.decompress((ROOT/"edge-switches.json.gz").read_bytes()))
    print(json.dumps(counts))

