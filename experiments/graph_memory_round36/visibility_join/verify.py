"""Verify all public SQLite states, timings, reader matching, and file inventory."""
from common import *
from sqlbench import reader,constraints
from operators import COSTD,CROSS
from degree_controls import DREAD
import sys
def run(seal):
    data=load(D/"input.json.gz");rows={h:z for h,z in data.items() if int(h)<128};assert len(rows)==128
    plan=load(D/"plan.json");ex=load(D/"extraction.json");assert ex["plan"]==sha(D/"plan.json") and ex["input"]==sha(D/"input.json.gz") and ex["reader"]==sha(D/"reader-checks.json.gz") and plan["protocol"]==sha(D/"PROTOCOL_RU.md")
    for name in ("flat","flat_shared","grouped"):
        con=reader(D/(name+".sqlite3"));assert constraints(con,name,rows)==512;con.close()
    for name,pair,degree in [("grouped_arity",CROSS,COSTD),("flat_delta",None,DREAD),("delta_only",None,DREAD)]:
        con=reader(D/(name+".sqlite3"))
        for h,z in rows.items():
            for s in z["checks"]:
                p={"h":int(h),"t":s["at"]};assert hashobj(con.execute(degree,p).fetchall())==s["degrees"]
                if pair:assert hashobj(con.execute(pair,p).fetchall())==s["pairs"]
        assert con.execute("PRAGMA integrity_check").fetchone()==("ok",);con.close()
    nr=load(D/"ranking-audit.json");assert nr["grouped_db"]==sha(D/"grouped.sqlite3") and nr["selections_checked"]=={"primary":2532,"extra":228}
    assert sha(D/"sqlbench.py")==load(D/"sql-plan.json")["code"] and sha(D/"operators.py")==load(D/"operator-plan.json")["script"] and sha(D/"degree_controls.py")==load(D/"degree-plan.json")["script"]
    for r in ("timings.json.gz","operator-timings.json.gz","degree-timings.json.gz"):
        x=load(D/r);vs=x.get("raw",x.get("reads_ns"));assert all(len(v[-1])==9 and min(v[-1])>0 for v in vs)
    p=D/"manifest.json"
    if seal:save(p,{"algorithm":"SHA-256","files":{f.name:sha(f) for f in sorted(D.iterdir()) if f.is_file() and f!=p}})
    records=load(p)["files"];assert set(records)=={f.name for f in D.iterdir() if f.is_file() and f!=p};assert all(sha(D/n)==h for n,h in records.items())
    print("Verified",len(records),"files;",sha(p))
if __name__=="__main__":run("--seal" in sys.argv)
