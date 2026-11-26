"""Run the published local top-k implementations on frozen Git deltas with independent read accounting."""
import argparse
from collections import Counter
import hashlib
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from generate import HERE,encode,read,save,sha

RESERVE=HERE.parent/"reserve"
sys.path.insert(0,str(RESERVE))
from reserve_store import InstrumentedCutoff,ReserveStore
from classic import ClassicStore
from core import KS,NOW

PLANS=("cutoff8","eager12","lazy12","classic12")
COLUMNS=("cold_probes","cold_rows","warm_probes","warm_rows","ordered_selects","ordered_rows","selects","select_rows","inserts","updates","returning_rows","sql","pairs")

class ObservedCursor:
    def __init__(self,cursor,event,is_select,is_ordered,is_returning):
        self.cursor=cursor
        self.event=event
        self.is_select=is_select
        self.is_ordered=is_ordered
        self.is_returning=is_returning
    def count(self,n):
        if self.is_select:self.event["select_rows"]+=n
        if self.is_ordered:self.event["ordered_rows"]+=n
        if self.is_returning:self.event["returning_rows"]+=n
    def fetchall(self):
        rows=self.cursor.fetchall();self.count(len(rows));return rows
    def fetchone(self):
        row=self.cursor.fetchone();self.count(int(row is not None));return row

class ObservedConnection(sqlite3.Connection):
    event=None
    def execute(self,sql,params=()):
        cursor=super().execute(sql,params)
        if self.event is None:return cursor
        statement=" ".join(sql.upper().split())
        op=statement.split(" ",1)[0]
        ordered=op=="SELECT" and "FROM SOURCE WHERE" in statement and "ORDER BY SCORE DESC,CID" in statement
        self.event["sql"]+=1
        if op in ("SELECT","INSERT","UPDATE"):self.event[op.lower()+"s"]+=1
        if ordered:self.event["ordered_selects"]+=1
        return ObservedCursor(cursor,self.event,op=="SELECT",ordered," RETURNING SCORE" in statement)
    def commit(self):
        if self.event is not None:self.event["sql"]+=1
        super().commit()

def opened(path):
    db=sqlite3.connect(path,isolation_level=None,factory=ObservedConnection)
    db.execute("PRAGMA journal_mode=WAL");db.execute("PRAGMA synchronous=NORMAL");db.execute("PRAGMA wal_autocheckpoint=0")
    return db

def method(db,name,create):
    if name=="classic12":return ClassicStore(db,12,create=create)
    if name=="cutoff8":return InstrumentedCutoff(db,"boundary",create=create)
    return ReserveStore(db,12,name[:-2],create=create)

def total(samples):
    return {key:sum(row[i] for row in samples) for i,key in enumerate(COLUMNS)}

def run(path,q,stream,refs,plan,repeat):
    db=opened(path);store=method(db,plan,True);events=[]
    try:
        explain=db.execute("EXPLAIN QUERY PLAN "+NOW,(q,8)).fetchall()
        assert any("COVERING INDEX source_best" in row[-1] for row in explain)
        base_size=None
        for row,ref in zip(stream,refs,strict=True):
            t=row["t"];transition=t-1
            if transition==1 or (repeat and transition>1 and (transition-1)%25==0):
                db.close();db=opened(path);store=method(db,plan,False)
            event=Counter();db.event=event
            assert store.update(q,row)
            db.event=None
            internal=store.event
            assert event["ordered_selects"]==internal["warm_probes"]+internal["cold_probes"]
            assert event["ordered_rows"]==internal["warm_rows"]+internal["cold_rows"]
            assert event["returning_rows"]==internal["score_rows"]
            for k in ("cold_probes","cold_rows","warm_probes","warm_rows","pairs"):event[k]=internal[k]
            if transition==1:assert event["cold_probes"]==1 and event["cold_rows"]>0
            events.append([event[k] for k in COLUMNS])
            # All checks below take place outside the observed method and come from independently parsed Git snapshots.
            current=db.execute("SELECT cid,score FROM source WHERE q=? ORDER BY score DESC,cid",(q,)).fetchall()
            edges=db.execute("SELECT src,dst FROM edge WHERE q=? AND end IS NULL AND weight=1 ORDER BY src,dst",(q,)).fetchall()
            assert hashlib.sha256(encode(current)).hexdigest()==ref["all_scores_sha"]
            assert hashlib.sha256(encode(edges)).hexdigest()==ref["active_edges_sha"]
            expected=[tuple(v) for v in ref["top8"]]
            if plan=="cutoff8":assert store.last[q][1]==expected
            else:
                cache=store.last[q][1][0]
                assert list(cache[:8])==expected
                if plan in ("eager12","classic12"):assert list(cache)==current[:len(cache)]
            assert store.get(q,t,8)==expected
            if t==1:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                base_size=path.stat().st_size
        for t,ref in enumerate(refs,1):
            for k in KS:
                want=[tuple(v) for v in ref["top8"][:k]]
                assert store._history(q,t,k)==want
                assert store.get(q,t,k)==want
        packets=db.execute("SELECT part,rev,hex(payload) FROM packet ORDER BY part,rev").fetchall()
        total_payload=db.execute("SELECT SUM(length(payload)) FROM packet").fetchone()[0]
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        size=path.stat().st_size
        metadata=dict(packet_rows=len(packets),packet_bytes=total_payload,packet_hash=hashlib.sha256(encode(packets)).hexdigest(),
            base_db_bytes=base_size,end_db_bytes=size,base=total(events[:1]),steady=total(events[1:]))
        return events,metadata
    finally:db.close()

def main(verify,scratch):
    for receipt in ("stream-seal.json","policy-seal.json"):
        assert all(sha(HERE/k)==v for k,v in read(receipt).items()),receipt
    streams=read("streams.json.gz");refs=read("snapshot-oracle.json.gz");raw={};results={}
    with TemporaryDirectory(dir=scratch) as tmp:
        for schedule in ("once","restart25"):
            raw[schedule]={};results[schedule]={}
            for plan in PLANS:
                costs={};checks={}
                for q,rows in streams.items():
                    path=Path(tmp)/(schedule+plan+q.replace("/","_")+".sqlite")
                    costs[q],checks[q]=run(path,q,rows,refs[q],plan,schedule=="restart25")
                raw[schedule][plan]=costs
                outcome=dict(per_repo=checks,base=total([ev[0] for ev in costs.values()]),
                    steady=total([x for ev in costs.values() for x in ev[1:]]),
                    graph_changed=total([costs[q][j] for q in streams for j,row in enumerate(streams[q]) if j and (row["delta"] or row["born"])]))
                results[schedule][plan]=outcome
                print(schedule,plan,outcome["steady"],flush=True)
    for q in streams:
        counts={(r["per_repo"][q]["packet_hash"],r["per_repo"][q]["end_db_bytes"]) for m in results.values() for r in m.values()}
        assert len(counts)==1
    save("event-costs.json.gz",dict(columns=COLUMNS,events=raw),verify)
    save("results.json",dict(sqlite=sqlite3.sqlite_version,schedules=results),verify)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify",action="store_true");parser.add_argument("--register",action="store_true")
    parser.add_argument("--scratch",type=Path,default=HERE);args=parser.parse_args()
    if args.register:
        assert not (HERE/"results.json").exists()
        pinned=["registration.json","replay.py","../reserve/classic.py"]
        save("policy-seal.json",{k:sha(HERE/k) for k in pinned})
    else:main(args.verify,args.scratch)
