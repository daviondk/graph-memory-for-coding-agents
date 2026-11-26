"""Derive exportable hashed inputs for three deliberately selected, real editor operations."""
from pathlib import Path
import json
import sqlite3
import sys
D=Path(__file__).resolve().parent
W=D.parents[1]
S=W/"graph_memory_round41/structural_invalidation"
L=D.parent/"context_edits"
sys.path.insert(0,str(S))
from shared import inputs,stream,case_id,signed,sha,h

def main():
    locked=signed(L,"predictions.json.gz");actions=signed(L,"action-lines.json.gz")
    structural=signed(S,"predictions.json.gz")
    cases={}
    for mode in ("edges","interior","changed"):
        options=[]
        for k,p in locked.items():
            if not p["held"] or not p["target_selected"]:continue
            old=p["old"];g=structural[k]["choices"]["range"];e=p["choices"]["edges"];c=p["choices"]["local"]
            flags={"edges":e==old and g!=old,"interior":c==old and e!=old,"changed":c!=old and len(c)<len(old)}
            if flags[mode]:
                options.append((len(actions[k]["old"])+len(actions[k]["new"]),len(old),k))
        k=min(options)[2]
        cases[k]=mode
    events,plans,views=inputs();wanted=[e for e in events if case_id(e) in cases]
    db=sqlite3.connect(":memory:");audit=sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE edit(id TEXT PRIMARY KEY, begin INTEGER, end INTEGER, delta INTEGER, argument_bytes INTEGER);
        CREATE TABLE literal(id TEXT, version INTEGER, n INTEGER, tag TEXT, PRIMARY KEY(id,version,n));
        CREATE TABLE node(id TEXT, unit INTEGER, affected INTEGER, lo INTEGER, hi INTEGER, cost INTEGER, gain INTEGER, PRIMARY KEY(id,unit));
    """)
    audit.executescript("""
        CREATE TABLE seen(id TEXT, unit INTEGER, n INTEGER, tag TEXT, PRIMARY KEY(id,unit,n));
        CREATE TABLE snapshot(id TEXT, version INTEGER, n INTEGER, tag TEXT, PRIMARY KEY(id,version,n));
    """)
    ref={}
    for k,e,_,old,new in stream(wanted):
        name=cases[k];att=actions[k]
        db.execute("INSERT INTO edit VALUES(?,?,?,?,?)",(name,e["start"],e["end"],e["delta"],att["bytes"]))
        for ver,v in enumerate(("old","new")):
            db.executemany("INSERT INTO literal VALUES(?,?,?,?)",((name,ver,i,x) for i,x in enumerate(att[v])))
        visible={n:d for n,d,*_ in views[e["run"]][str(e["view"])]}
        plan=plans[e["run"]][str(e["at"])][0]
        addresses=[set(),set()]
        for i,path,lo,hi,c,u,_ in plan:
            affected=path==e["path"]
            db.execute("INSERT INTO node VALUES(?,?,?,?,?,?,?)",(name,i,affected,lo,hi,c,u))
            if affected:
                for n in range(lo,hi+1):
                    audit.execute("INSERT INTO seen VALUES(?,?,?,?)",(name,i,n,visible[n]))
                    addresses[0].add(n)
        p=locked[k]
        for dest in p["positions"]["local"].values():
            addresses[1].update(range(dest[0],dest[1]+1))
        for v,text in enumerate([old,new]):
            lines=text.split("\n")
            for n in sorted(addresses[v]):
                audit.execute("INSERT INTO snapshot VALUES(?,?,?,?)",(name,v,n,h(lines[n-1])))
        ref[name]=dict(case_sha=k,prior=p["old"],file=structural[k]["choices"]["file"],
            range=structural[k]["choices"]["range"],edges=p["choices"]["edges"],local=p["choices"]["local"])
    for conn,filename in [(db,"reader.sqlite"),(audit,"audit.sqlite")]:
        conn.commit()
        with sqlite3.connect(D/filename) as dest:conn.backup(dest)
        conn.close()
    (D/"reference.json").write_text(json.dumps(ref,indent=2,sort_keys=True)+"\n",encoding="utf8")
    print(ref)
if __name__=="__main__":main()
