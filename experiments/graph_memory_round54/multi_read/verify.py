"""Reopen every database and compare historical and current plans to an independent graph replay."""
from tempfile import TemporaryDirectory
from analyze import analyze
from bench import *
def verify():
    reg=load("registration.json")
    assert reg["work"]==sha(OLD/"workload.json.gz") and reg["prior"]==sha(OLD/"registration.json")
    assert reg["protocol"]==sha(D/"PROTOCOL_RU.md") and all(reg["code"][n]==sha(D/n) for n in reg["code"])
    work,refs,stats=prepare();exact=load("exactness.json")
    assert exact["logical"]==dict(stats)
    completed=0;history=0
    with TemporaryDirectory() as td:
        for plan in PLANS:
            fname=Path(td)/(plan+".db");db=connect(fname);s=Store(db,plan)
            for q,events in work.items():
                for r in events:assert s.update(q,r)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone();direct=storage(db,plan);db.close()
            db=connect(fname);fresh=Store(db,plan,False)
            try:
                for q,vers in refs.items():
                    for j,vector in enumerate(vers):
                        for k in KS:
                            assert fresh.get(q,j,k)==vector[:k]
                            assert fresh._history(q,j,k)==vector[:k]
                            completed+=1;history+=1
                for name,v in direct.items():assert exact["plans"][plan][name]==v
                if plan=="admitted":
                    closed=db.execute("SELECT COUNT(*) FROM cv WHERE end IS NOT NULL").fetchone()[0]
                    assert stats["closures"]==closed
                assert fname.stat().st_size==exact["plans"][plan]["bytes"]
            finally:db.close()
    assert completed==3*5*1112
    analyze(False)
    result=dict(k=list(KS),witnesses=completed,history_paths_including_current=history,versions=1112,
                rollbacks_and_conflicting_receipts="verified by original isolated two-writer q11 replay per plan",
                mean_ratio_check=sha(D/"results.json"),code=sha(Path(__file__)))
    print(json.dumps(result))
    return result
if __name__=="__main__":
    import sys
    z=verify()
    if "--save" in sys.argv:save("verification.json",z)
    else:assert z==load("verification.json")
