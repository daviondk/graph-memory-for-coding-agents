"""Independently test temporal lookup, transaction failure, concurrent readers and restore/replay."""
from pathlib import Path
import sqlite3
import tempfile
from collections import Counter
from engine import Engine,connect
from source import HERE,WORK,read,save,sha

A=[0,1,2];R1=[[0,2,2]]
R2=[[0,2,-2],[1,2,3],[0,1,1],[0,1,-1]]
R3=[[0,2,3]];R4=[[0,2,2]];R5=[[0,2,-5],[1,2,-3]]
STEPS=[(A,R1),([],R2),([],R3),([],R4),([],R5),([],[[1,2,3]])]
EXPECT=[None,(0,2),(1,3),(0,3),(0,5),(0,0),(1,3)]
def fail(fn,kind):
    try:fn()
    except kind:return
    raise AssertionError("expected "+kind.__name__)
def counts(c,p):
    tbls=["source","edge","receipt","head","winner"]+(["cv"] if p=="candidate" else [])
    return [list(c.execute("SELECT * FROM "+t+" ORDER BY 1,2")) for t in tbls]
def proofs(plan,temp):
    writer=connect(temp/(plan+".sqlite"));x=Engine(writer,plan,create=True)
    other=connect(temp/(plan+".sqlite"));observer=Engine(other,plan)
    q="unit"
    assert x.get(q,0) is None and x.apply(q,1,A,R1)
    snap=sqlite3.connect(temp/(plan+"-backup.sqlite"));writer.backup(snap)
    # Force a commit on the second handle BETWEEN the read's version lookup and result SELECT.
    injected=[]
    def switch(statement):
        if "SELECT cid,score FROM source" in statement and not injected:
            injected.append(True)
            x.apply(q,2,[],R2)
    other.set_trace_callback(switch)
    assert observer.get(q,1)==EXPECT[1] and injected
    other.set_trace_callback(None)
    assert observer.get(q,2)==EXPECT[2]
    # Hold a longer external read transaction; new versions are invisible until that transaction finishes.
    other.execute("BEGIN")
    assert observer.get(q,2)==EXPECT[2]
    x.apply(q,3,[],R3);fail(lambda:observer.get(q,3),ValueError)
    assert observer.get(q,2)==EXPECT[2]
    other.commit();assert observer.get(q,3)==EXPECT[3]
    before=counts(writer,plan)
    assert x.apply(q,2,[],list(reversed(R2))) is False and before==counts(writer,plan)
    fail(lambda:x.apply(q,2,[],[[1,2,4]]),ValueError)
    fail(lambda:x.apply(q,5,[],R4),ValueError)
    fail(lambda:x.apply(q,4,[],[[0,1,1],[1,2,-50]]),ValueError)
    fail(lambda:x.apply(q,4,[],R4,fail_after_edges=True),RuntimeError)
    assert before==counts(writer,plan)
    for t in (4,5,6):x.apply(q,t,*STEPS[t-1])
    assert [x.get(q,t) for t in range(7)]==EXPECT
    after=counts(writer,plan)
    # Restore the real checkpoint into the SAME target DB after closing the observing connection.
    other.close();snap.backup(writer);snap.close()
    assert x.get(q,1)==EXPECT[1];fail(lambda:x.get(q,2),ValueError)
    for t in range(2,7):assert x.apply(q,t,*STEPS[t-1])
    assert counts(writer,plan)==after
    writer.close()
    reopened=connect(temp/(plan+".sqlite"));z=Engine(reopened,plan)
    assert [z.get(q,t) for t in range(7)]==EXPECT
    assert reopened.execute("PRAGMA integrity_check").fetchone()==("ok",)
    reopened.close()
    return dict(same_revision_compensation=True,committed_between_version_and_value=True,long_reader_snapshot=True,
                identical_retry=True,conflicting_retry_rollback=True,gap_rejected=True,negative_weight_rollback=True,
                mid_transaction_failure_rollback=True,snapshot_restore_and_reapply=True,reopened_all_versions=True)

def independent(work):
    with tempfile.TemporaryDirectory(dir=WORK if WORK.is_dir() else None) as tmp:
        db=connect(Path(tmp)/"reference.sqlite");engine=Engine(db,"journal",create=True);versions=ops=0
        for q,frames in sorted(work.items()):
            for f in frames:engine.apply(q,f["t"],f["born"],f["delta"])
            for t in range(len(frames)+1):
                available=set();edges=Counter()
                for f in frames[:t]:
                    available.update(f["born"])
                    for a,b,change in f["delta"]:edges[a,b]+=change;ops+=1
                score={v:sum(w for (src,_),w in edges.items() if src==v) for v in available}
                if not score:expected=None
                else:
                    greatest=max(score.values());expected=(min(v for v in score if score[v]==greatest),greatest)
                assert engine.get(q,t)==expected
                # Reconstruct every edge's final multiplicity at every version from SQL validity intervals.
                observed={(a,b):w for a,b,w in db.execute("SELECT src,dst,weight FROM edge WHERE q=? AND beg<=? AND (end IS NULL OR end>?)",(q,t,t))}
                assert observed=={p:v for p,v in edges.items() if v}
                versions+=1
        db.close();return versions
def main():
    with tempfile.TemporaryDirectory(dir=WORK if WORK.is_dir() else None) as tmp:
        checks={p:proofs(p,Path(tmp)) for p in ("interval","candidate","journal")}
    n=independent(read(HERE/"workload.json.gz"))
    reports=read(HERE/"results.json");assert n==reports["n_versions_verified_including_empty"]
    save("verification.json",{"checks":checks,"natural_versions_reconstructed_from_start":n,
         "all_source_edge_intervals_and_winner_pairs":True,"engine_sha":sha((HERE/"engine.py").read_bytes()),"state":"PASS"})
    print("PASS",n, len(checks))
if __name__=="__main__":main()

