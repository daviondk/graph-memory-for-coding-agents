"""Build anonymous temporal relations from the replay, then verify as-of reads."""
import json
import os
import sqlite3
import sys
from pathlib import Path
from store import DATA,SCHEMA,view,connect
sys.path.insert(0,str(DATA.parent.parent/"incremental_binding"))
from evaluate import env, parse_isetrace_record, adapt_isetrace_record, FeedIndex, edge_hash, save


from graph_memory.graphs.provenance.builder import _typed_tokens, _argument_contains


def changes_before_event(index,event,alias):
    # Capture only values that support at least one actual edge. Aliases are local to each history.
    reasons=[]
    if event.event_type=="tool_call":
        pos=(event.position.message_index,event.position.sub_index)
        for value,entry in sorted(index.values.items()):
            if entry and entry.position<pos and _argument_contains(event,value):
                v=alias.setdefault(value,len(alias)+1)
                reasons.append((entry.source,event.call_id,v,"match",None))
    elif event.event_type=="tool_output":
        for _,value in sorted(_typed_tokens(event.content)):
            entry=index.values.get(value)
            if entry and entry.source!=event.call_id:
                for consumer in sorted(entry.readers):
                    reasons.append((entry.source,consumer,alias[value],"ambiguous",event.call_id))
    return reasons


def main():
    source_dir=DATA.parent.parent/"incremental_binding"
    receipts={r["t"]:r for r in env.load(source_dir/"prefix-outcomes.json.gz")}
    staged=DATA.with_suffix(".building.sqlite")
    if staged.exists():raise FileExistsError(staged)
    db=sqlite3.connect(staged);db.executescript(SCHEMA)
    verified=0;seen=set()
    for shard in range(8):
        source=env.RAW/f"trajectories-{shard:05d}.jsonl"
        for blob,obj in env.pilot.stream(source):
            t=obj["session_id"]
            if t not in receipts:continue
            rec=receipts[t];assert env.hashlib.sha256(blob).hexdigest()==rec["source_sha256"]
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            live=FeedIndex();names={};steps={};slots={};aliases={};proof={}
            with db:
                db.execute("INSERT INTO trace VALUES(?,?)",(t,len(tr.events)))
                for j,e in enumerate(tr.events):
                    known=dict(live.support);reasons=changes_before_event(live,e,aliases);live.consume(e)
                    if e.event_type=="tool_call":
                        names[e.call_id]=len(names)+1;steps[e.call_id]=[j,None]
                    elif e.event_type=="tool_output":
                        steps[e.call_id][1]=j
                    db.execute("INSERT INTO event VALUES(?,?,?,?)",(t,j,e.event_type,names.get(getattr(e,"call_id",None))))
                    for a,b,v,cause,other in reasons:
                        pair=(a,b)
                        if cause=="match":proof.setdefault(pair,set()).add(v)
                        else:
                            proof[pair].remove(v)
                            if not proof[pair]:del proof[pair]
                        db.execute("INSERT INTO reason VALUES(?,?,?,?,?,?,?)",(t,names[a],names[b],j,v,cause,names.get(other)))
                    assert {p:len(vals) for p,vals in proof.items()}==dict(live.support)
                    for a,b in sorted(known.keys()|live.support.keys()):
                        old,new=known.get((a,b),0),live.support.get((a,b),0)
                        if new==old:continue
                        u,v=names[a],names[b]
                        if old:
                            affected=db.execute("UPDATE witness SET hi=? WHERE t=? AND a=? AND b=? AND lo=? AND hi IS NULL",
                                       (j,t,u,v,slots.pop((a,b)))).rowcount
                            assert affected==1
                        if new:
                            db.execute("INSERT INTO witness VALUES(?,?,?,?,NULL,?)",(t,u,v,j,new));slots[(a,b)]=j
                db.executemany("INSERT INTO endpoint VALUES(?,?,?,?)",[(t,n,*steps[a]) for a,n in names.items()])
                db.executemany("INSERT INTO checkpoint VALUES(?,?,?,?)",[(t,r["index"],int(r["last"]),r["gold"]) for r in rec["records"]])
            by_number={v:k for k,v in names.items()}
            for r in rec["records"]:
                snap=view(db,t,r["index"])
                for old,new in (("counted","exact"),("append","append"),("retrospective","final")):
                    pairs={(by_number[z["a"]],by_number[z["b"]]) for z in snap["edges"] if z[new]}
                    assert edge_hash(pairs)==r["arms"][old]["sha"],(t,r["index"],old)
                    verified+=1
            seen.add(t)
    assert seen==set(receipts) and verified==383*3
    counts={tab:db.execute(f"SELECT COUNT(*) FROM {tab}").fetchone()[0] for tab in ("trace","event","endpoint","witness","checkpoint","reason")}
    assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    db.execute("VACUUM");db.close();os.replace(staged,DATA)
    reader=connect()
    assert reader.execute("SELECT count(*) FROM trace").fetchone()==(96,)
    reader.close()
    save(DATA.with_name("verification.json"),{"tables":counts,"native_asof_set_hashes_verified":verified,"sqlite_bytes":DATA.stat().st_size,
        "database_sha256":env.pilot.sha(DATA),"reference_outcomes":env.pilot.sha(source_dir/"prefix-outcomes.json.gz"),
        "store":env.pilot.sha(DATA.with_name("store.py")),"builder":env.pilot.sha(Path(__file__))})
    print(counts,verified,flush=True)

if __name__=="__main__":main()
