"""Immutable event frames, a durable SQL tail, separate revision receipts and a matching full posting list."""
from collections import defaultdict
from itertools import groupby
import sqlite3
import zlib

from block_store import BlockStore, BYTE_APPEND, SCHEMAS, varints

FRAME_MODES=("plain8","compressed8","plain64","compressed64")


def encode_frame(bodies):
    return b"".join(varints((len(body),)) + body for body in bodies)


def slices(frame, positions):
    result=[]
    position=offset=0
    needed=iter(positions)
    target=next(needed,None)
    while target is not None:
        if offset>=len(frame):raise ValueError("missing source frame length")
        size=frame[offset];offset+=1
        if size>=128:
            size&=127;shift=7
            while True:
                byte=frame[offset];offset+=1;size|=(byte&127)<<shift
                if byte<128:break
                shift+=7
        end=offset+size
        if end>len(frame):raise ValueError("truncated event")
        if position==target:
            result.append(frame[offset:end]);target=next(needed,None)
        offset=end;position+=1
    return result


class FrameStore(BlockStore):
    def __init__(self,path,mode,create=False):
        if mode not in FRAME_MODES:raise ValueError(mode)
        self.mode="filelist"  # Reuse the identical exact reverse-list query.
        self.width=64 if mode.endswith("64") else 8
        self.compress=mode.startswith("compressed")
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL").fetchone()
        self.db.execute("PRAGMA synchronous=FULL")
        if create:
            self.db.execute("CREATE TABLE tail(j INTEGER PRIMARY KEY,rev BLOB NOT NULL,v BLOB NOT NULL)")
            self.db.execute("CREATE TABLE frame(b INTEGER PRIMARY KEY,revs BLOB NOT NULL,compressed INTEGER NOT NULL,v BLOB NOT NULL)")
            self.db.execute(SCHEMAS["filelist"])
        self.next_id=self.db.execute("SELECT MAX((SELECT ifnull(max(j),-1)+1 FROM tail),"
                                     "(SELECT (ifnull(max(b),-1)+1)*? FROM frame))",(self.width,)).fetchone()[0]
        self.incident=defaultdict(list);self.tail={}
        self.metadata_rows=self.metadata_bytes=0
        self.src_rows=self.src_blobs=self.src_bytes=0
        self.restore_rows=self.restore_payload=self.restore_source_bytes=0

    def get_event(self,j):
        boundary=self.next_id//self.width*self.width
        if j>=boundary:return self.db.execute("SELECT rev,v FROM tail WHERE j=?",(j,)).fetchone()
        b,position=divmod(j,self.width)
        row=self.db.execute("SELECT substr(revs,?,20),compressed,v FROM frame WHERE b=?",(position*20+1,b)).fetchone()
        if row is None:return None
        rev,compressed,raw=row
        body=zlib.decompress(raw) if compressed else raw
        return rev,slices(body,(position,))[0]

    def append(self,j,rev,ids,fault=False):
        ids=tuple(ids);raw_sha=bytes.fromhex(rev)
        if len(raw_sha)!=20 or len(ids)<2 or len(ids)!=len(set(ids)):raise ValueError("invalid event")
        data=varints(ids)
        if j<self.next_id:
            if self.get_event(j)!=(raw_sha,data):raise ValueError("conflicting replay")
            return False
        if j!=self.next_id:raise ValueError("event gap")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if (j+1)%self.width:
                self.db.execute("INSERT INTO tail VALUES(?,?,?)",(j,raw_sha,data))
            else:
                rows=self.db.execute("SELECT rev,v FROM tail ORDER BY j").fetchall()
                if len(rows)!=self.width-1:raise ValueError("invalid source tail")
                rows.append((raw_sha,data))
                shas,bodies=zip(*rows)
                packed=encode_frame(bodies)
                smaller=False
                if self.compress:
                    candidate=zlib.compress(packed,1)
                    if len(candidate)<len(packed):
                        packed=candidate;smaller=True
                self.db.execute("INSERT INTO frame VALUES(?,?,?,?)",(j//self.width,b"".join(shas),smaller,packed))
                self.db.execute("DELETE FROM tail")
            pointer=varints((j,))
            self.db.executemany(BYTE_APPEND,((f,pointer) for f in ids))
            if fault:raise RuntimeError("injected rollback")
            self.db.commit()
        except BaseException:
            self.db.rollback();raise
        self.next_id+=1
        return True

    def _fetch_events(self,ids):
        if not ids:return [],0
        boundary=self.next_id//self.width*self.width
        frames=defaultdict(list);remaining=[]
        for j in ids:
            if j>=boundary:remaining.append(j)
            else:
                b,offset=divmod(j,self.width)
                frames[b].append(offset)
        out=[];calls=0
        keys=list(frames)
        for start in range(0,len(keys),400):
            chunk=keys[start:start+400];binds=",".join("?" for _ in chunk)
            for b,c,raw in self.db.execute("SELECT b,compressed,v FROM frame WHERE b IN ("+binds+")",chunk):
                self.src_rows+=1;self.src_blobs+=1;self.src_bytes+=len(raw)
                body=zlib.decompress(raw) if c else raw
                out.extend((data,) for data in slices(body,frames[b]))
            calls+=1
        if remaining:
            binds=",".join("?" for _ in remaining)
            rows=self.db.execute("SELECT v FROM tail WHERE j IN ("+binds+")",remaining).fetchall()
            self.src_rows+=len(rows);self.src_blobs+=len(rows);self.src_bytes+=sum(len(raw) for raw, in rows)
            out.extend(rows);calls+=1
        return out,calls
