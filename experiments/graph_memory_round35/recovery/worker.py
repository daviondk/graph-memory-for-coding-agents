"""Only the process launched with role 'crash' exits its own PID abruptly."""
import os,sys
from support import *
def apply(db,pending,row,finish=True):
    seq,cut,adds,drops=row
    pending.difference_update(adds);pending.update(drops)
    if not adds and not cut:return 0
    db.execute("BEGIN IMMEDIATE")
    changed=db.total_changes
    db.executemany("INSERT OR IGNORE INTO edge(id) VALUES(?)",((i,) for i in adds))
    inserts=db.total_changes-changed
    if cut:
        db.executemany("DELETE FROM edge WHERE id=?",((i,) for i in sorted(pending)))
        db.execute("UPDATE barrier SET seq=? WHERE id=1",(seq,));pending.clear()
    if finish:db.execute("COMMIT")
    return len(adds)-inserts
def stage(role,case,folder):
    src=source();h=case["history"];at=case["received"];paths=[folder/(m+".sqlite3") for m in ("naive","replay")]
    if role=="crash":
        conns=[openbase(p) for p in paths];pend=[set(),set()]
        for row in fetch(src,h,0,at):
            for db,p in zip(conns,pend):apply(db,p,row)
        assert pend[0]==pend[1] and snapshot(conns[0])==snapshot(conns[1]) and watermark(conns[0])==case["barrier"]
        submitted=False;at_barrier=case["type"]=="uncommitted_first"
        if at_barrier:
            row=next(fetch(src,h,at,at+1));assert row[1]
            for db,p in zip(conns,pend):apply(db,p,row,finish=False)
            assert all(db.in_transaction and watermark(db)==at+1 for db in conns);submitted=True
        print(json.dumps({"pid":os.getpid(),"uncommitted_visible_in_writer":submitted,"wal_bytes":[Path(str(p)+"-wal").stat().st_size for p in paths],"in_transaction":[db.in_transaction for db in conns]}),flush=True)
        os._exit(73)
    assert role=="restart";res={}
    for m,path in zip(["naive","replay"],paths):
        db=newdb(path);ok=db.execute("PRAGMA integrity_check").fetchone()[0];assert ok=="ok"
        b=watermark(db);initial=snapshot(db);pend=set();checked=[];done=adds=rm=ignored=range_queries=0
        if m=="replay":
            range_queries+=1
            for row in fetch(src,h,b,at):
                assert not row[1];done+=1;adds+=len(row[2]);rm+=len(row[3]);ignored+=apply(db,pend,row)
        for row in fetch(src,h,at,case["n"]):
            apply(db,pend,row)
            if row[1]:checked.append([row[0],snapshot(db)])
        assert not pend
        res[m]={"initial":initial,"b":b,"reads":checked,"terminal":snapshot(db),"replayed_rows":done,"up":adds,"down":rm,"ignored_inserts":ignored,"replay_selects":range_queries,"final_b":watermark(db),"integrity":ok}
        db.close()
    print(json.dumps({"pid":os.getpid(),"branches":res},separators=(",",":")),flush=True)
if __name__=="__main__":stage(sys.argv[1],json.loads(sys.argv[2]),Path(sys.argv[3]))
