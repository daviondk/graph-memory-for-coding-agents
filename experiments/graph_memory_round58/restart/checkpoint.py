"""A checksummed, source-bound snapshot and an exact filelist reader."""
from collections import Counter, defaultdict, deque
from fractions import Fraction
from pathlib import Path
import struct
import sys
import zlib

R57=Path(__file__).resolve().parents[2]/"graph_memory_round57"
sys.path.insert(0,str(R57/"composed"))
from reader import Reader, best, unpack
from block_store import varints

BASE=struct.Struct("<4sI20sII")
CRC=struct.Struct("<I")
HEADER=BASE.size+CRC.size
MAGIC=b"GES1"


class Demand:
    def __init__(self):
        self.window=deque();self.counts=Counter()

    def append(self,ids):
        if len(self.window)==128:
            for f in self.window.popleft():
                self.counts[f]-=1
                if not self.counts[f]:del self.counts[f]
        self.window.append(ids);self.counts.update(ids)


def make_snapshot(live,fence,revision,policy,cap,demand=None):
    rows=[]
    for j,ids in live.items():
        body=varints(ids)
        entry=varints((j,len(body)))+body
        if policy=="demand":
            score=Fraction(len(body)*sum(1+demand.counts[f] for f in ids),len(entry))
        elif policy=="largest":score=len(body)
        else:score=j
        rows.append((score,j,entry))
    avail=None if cap is None else cap-HEADER
    if avail is not None and avail<0:raise ValueError("header exceeds capacity")
    kept=[]
    for score,j,entry in sorted(rows,reverse=True):
        if avail is None or len(entry)<=avail:
            kept.append((j,entry))
            if avail is not None:avail-=len(entry)
    body=b"".join(entry for j,entry in sorted(kept))
    header=BASE.pack(MAGIC,fence,bytes.fromhex(revision),len(kept),len(body))
    if cap is not None:body+=bytes(avail)
    message=header+body
    return message+CRC.pack(zlib.crc32(message)),len(kept),sum(len(e) for _,e in kept)+HEADER


def take_int(data,pos,end):
    start=pos;value=shift=0
    while pos<end and pos-start<10:
        c=data[pos];pos+=1
        value|=(c&127)<<shift
        if c<128:return value,pos
        shift+=7
    raise ValueError("invalid snapshot varint")


def unpack_snapshot(blob,fence,raw_sha):
    if len(blob)<HEADER or zlib.crc32(blob[:-CRC.size])!=CRC.unpack(blob[-CRC.size:])[0]:
        raise ValueError("invalid snapshot checksum")
    magic,other,sha,number,size=BASE.unpack_from(blob)
    if magic!=MAGIC or fence!=other or sha!=raw_sha:raise ValueError("snapshot source mismatch")
    pos=BASE.size;end=pos+size
    if end>len(blob)-CRC.size or number>size:raise ValueError("invalid snapshot envelope")
    events={};previous=-1
    for _ in range(number):
        j,pos=take_int(blob,pos,end);sz,pos=take_int(blob,pos,end)
        if not previous<j<fence or pos+sz>end:raise ValueError("invalid snapshot event")
        ids=unpack(blob[pos:pos+sz])
        if len(ids)<2 or len(set(ids))!=len(ids):raise ValueError("invalid event body")
        pos+=sz;events[j]=ids;previous=j
    if pos!=end or any(blob[end:-CRC.size]):raise ValueError("invalid padding or record size")
    return events


def persist(db,blob):
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("CREATE TABLE IF NOT EXISTS snapshot(k INTEGER PRIMARY KEY CHECK(k=1),v BLOB NOT NULL)")
        db.execute("INSERT OR REPLACE INTO snapshot VALUES(1,?)",(blob,))
        db.commit()
    except BaseException:
        db.rollback();raise


class Pinned(Reader):
    def __init__(self,path,restore):
        super().__init__(path,"shared")
        self.pinned={};self.pinned_for=defaultdict(set);self.complete=set()
        self.loaded_bytes=self.receipt_bytes=self.open_calls=0
        self.rejected=False
        if restore:self.restore()

    def restore(self):
        self.open_calls+=1
        # This catalog lookup also makes interrupted checkpoint creation recoverable.
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshot'").fetchone():return
        self.open_calls+=1
        rec=self.db.execute("SELECT v FROM snapshot WHERE k=1").fetchone()
        if not rec:return
        blob=rec[0];self.loaded_bytes=len(blob);self.open_calls+=1
        current=self.db.execute("SELECT rev FROM event WHERE j=?",(self.fence-1,)).fetchone()
        sha=current[0] if current else b""
        self.receipt_bytes=len(sha)
        try:self.pinned=unpack_snapshot(blob,self.fence,sha)
        except ValueError:
            self.rejected=True;return
        for j,ids in self.pinned.items():
            for f in ids:self.pinned_for[f].add(j)

    def read(self,f,tie,prior):
        pre=self.pinned_for.get(f,())
        post=self.hot.incident.get(f,())
        counts=Counter()
        for j in pre:counts.update(self.pinned[j])
        for j in post:counts.update(self.hot.live[j])
        if f in self.complete and f not in self.hot.lost_shared:
            return best(counts,f,tie,prior),(0,0,0,0,0,len(pre),len(post))
        row=self.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
        if not row:
            self.complete.add(f)
            return best(counts,f,tie,prior),(1,0,0,0,0,len(pre),len(post))
        js=unpack(row[0])
        if f not in self.complete and all(j in pre for j in js if j<self.fence):
            self.complete.add(f)
        missing=[j for j in js if j not in pre and j not in post]
        rows,calls=self.store._fetch_events(missing)
        nbytes=0
        for blob, in rows:nbytes+=len(blob);counts.update(unpack(blob))
        return best(counts,f,tie,prior),(1,calls,len(row[0]),len(rows),nbytes,len(pre),len(post))
