"""Observe SQLite BLOBs at the caller boundary on four real project workloads."""
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory

from check_refs import HERE, inputs, selections
from bench import prepare
from ref_reader import ReferenceReader
from block_store import BlockStore
from packet import encode
from checkpoint import persist


class Buffered:
    def __init__(self, rows):
        self.rows=rows

    def fetchone(self):
        return next(iter(self.rows),None)

    def __iter__(self):
        return iter(self.rows)


class Meter:
    def __init__(self, db):
        self.db=db
        self.payload=Counter()
        self.calls=Counter()

    def execute(self, sql, params=()):
        cursor=self.db.execute(sql,params)
        head=sql.upper().split(" FROM ",1)[0].strip()
        kinds={"SELECT V":"snapshot","SELECT REV":"revision","SELECT JS":"posting","SELECT MEMBERS":"source"}
        if head not in kinds:
            return cursor
        kind=kinds[head]
        rows=cursor.fetchall()
        self.calls[kind]+=1
        self.payload[kind]+=sum(len(row[0]) for row in rows)
        return Buffered(rows)


class Observed(ReferenceReader):
    def open_snapshot(self):
        self.db=Meter(self.db)
        super().open_snapshot()


def run():
    results={}
    projects={"original":"sphinx-doc/sphinx","replication":"python-babel/babel","seed_pair":"dask/dask"}
    with TemporaryDirectory(dir=HERE) as temp:
        folder=Path(temp)
        for origin,panel,project,stream in inputs():
            if project!=projects[origin] or not (panel=="long" or origin=="replication"):
                continue
            ops,_=prepare(stream,panel)
            writes=[v for v in ops if v[0]=="w"]
            fence=len(writes)//2
            split=next(i+1 for i,x in enumerate(ops) if x[0]=="w" and x[1]==fence-1)
            prefix=folder/"prefix.sqlite"
            with closing(BlockStore(prefix,"filelist",True)) as db:
                for _,j,rev,ids in writes[:fence]:
                    assert db.append(j,rev,ids)
                assert db.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
            history=[x[-1] for x in writes[:fence]]
            options=selections(history)
            options["alternate"]=set(range(0,fence,3))
            options["empty"]=set()
            key="/".join((origin,panel,project))
            results[key]={}
            for label,keep in options.items():
                arms={}
                members={j:history[j] for j in keep}
                for mode in ("copy","compressed","eager","lazy"):
                    target=folder/"current.sqlite"
                    shutil.copyfile(prefix,target)
                    blob=encode(members,fence,writes[fence-1][2],mode)
                    with closing(sqlite3.connect(target)) as db:
                        persist(db,blob)
                        stored=db.execute("SELECT length(v) FROM snapshot").fetchone()[0]
                    with closing(Observed(target,mode)) as h:
                        assert h.selected==keep
                        meter=h.db
                        open_bytes=meter.payload.copy()
                        first=0
                        digest=hashlib.sha256()
                        n=0
                        for op in ops[split:]:
                            if op[0]=="w":
                                assert h.append(*op[1:])
                                continue
                            _,f,tie,prior,reference=op
                            past=meter.payload.copy()
                            answer,work=h.read(f,tie,prior)
                            assert answer==reference
                            assert meter.payload["source"]-past["source"]==work[3]
                            assert meter.payload["posting"]-past["posting"]==work[1]
                            first+=work[4]
                            digest.update(json.dumps(answer,separators=(",",":")).encode()+b"\n")
                            n+=1
                        arms[mode]=dict(stored=stored,received=dict(meter.payload),
                                       sql=dict(meter.calls),opening=dict(open_bytes),
                                       first_touch=first,charged=stored+sum(meter.payload.values()),
                                       queries=n,ranking_sha=digest.hexdigest())
                    target.unlink()
                lazy=arms["lazy"]
                for name,v in arms.items():
                    assert v["ranking_sha"]==lazy["ranking_sha"]
                    if name in ("copy","compressed"):
                        assert v["charged"]-lazy["charged"]==2*(v["stored"]-lazy["stored"])-lazy["first_touch"]
                results[key][label]=arms
            prefix.unlink()
    return results


if __name__=="__main__":
    out=run()
    p=HERE/"meter.json"
    if "--verify" in sys.argv:
        assert json.loads(p.read_bytes())==out
    else:
        p.write_text(json.dumps(out,indent=1,sort_keys=True)+"\n",encoding="utf8")
    n=sum(a["queries"] for groups in out.values() for block in groups.values() for a in block.values())
    print("Real source workloads",len(out),"measured rankings",n)
