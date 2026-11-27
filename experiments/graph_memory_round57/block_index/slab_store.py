"""A durable packed source journal with appendable 64-event directory and data columns."""
from collections import Counter, defaultdict
from itertools import groupby
import sqlite3
import struct

from block_store import BLOCK, BYTE_APPEND, BlockStore, SCHEMAS, unpack, varints

NEW_MODES=("slab_filelist","slab_sealed_list")
UPSERT="""INSERT INTO slab VALUES(?,1,?,?,?)
ON CONFLICT(b) DO UPDATE SET n=n+1,sha=CAST(sha||excluded.sha AS BLOB),
ends=CAST(ends||excluded.ends AS BLOB),body=CAST(body||excluded.body AS BLOB)"""
SCHEMA="""CREATE TABLE slab(b INTEGER PRIMARY KEY,n INTEGER NOT NULL,sha BLOB NOT NULL,
ends BLOB NOT NULL,body BLOB NOT NULL)"""


def member_slice(offsets, data, position):
    stop=struct.unpack_from("<I",offsets,position*4)[0]
    start=struct.unpack_from("<I",offsets,(position-1)*4)[0] if position else 0
    return data[start:stop]


class SlabStore(BlockStore):
    def __init__(self,path,mode,create=False):
        if mode not in NEW_MODES:raise ValueError(mode)
        self.mode=mode.removeprefix("slab_")
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL").fetchone()
        self.db.execute("PRAGMA synchronous=FULL")
        if create:
            self.db.execute(SCHEMA)
            self.db.execute(SCHEMAS["filelist"])
        self.tail={};self.incident=defaultdict(list)
        self.metadata_rows=self.metadata_bytes=0
        self.src_blobs=self.src_bytes=self.src_rows=0
        self.restore_rows=self.restore_payload=self.restore_source_bytes=0
        last=self.db.execute("SELECT b,n,length(body) FROM slab ORDER BY b DESC LIMIT 1").fetchone()
        self.next_id=0 if last is None else last[0]*BLOCK+last[1]
        self.offset=last[2] if self.next_id % BLOCK else 0
        if self.mode=="sealed_list" and self.next_id % BLOCK:
            b,n,_=last
            ends,body=self.db.execute("SELECT ends,body FROM slab WHERE b=?",(b,)).fetchone()
            self.restore_source_bytes=len(ends)+len(body)
            for ix in range(n):
                data=member_slice(ends,body,ix)
                self._retain(b*BLOCK+ix,unpack(data))
                self.restore_payload+=len(data);self.restore_rows+=1

    def get_event(self,j):
        page,pos=divmod(j,BLOCK)
        row=self.db.execute("SELECT n,substr(sha,?,20),ends,body FROM slab WHERE b=?",
                            (pos*20+1,page)).fetchone()
        if row is None or pos>=row[0]:return None
        return row[1],member_slice(row[2],row[3],pos)

    def append(self,j,rev,ids,fault=False):
        ids=tuple(ids);raw_sha=bytes.fromhex(rev)
        if len(raw_sha)!=20 or len(ids)<2 or len(ids)!=len(set(ids)):raise ValueError("invalid event")
        payload=varints(ids)
        if j<self.next_id:
            if self.get_event(j)!=(raw_sha,payload):raise ValueError("conflicting replay")
            return False
        if j!=self.next_id:raise ValueError("event gap")
        block,pos=divmod(j,BLOCK);seal=pos==BLOCK-1
        stop=self.offset+len(payload)
        if stop>0xffffffff:raise OverflowError("source block exceeds uint32 directory capacity")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(UPSERT,(block,raw_sha,struct.pack("<I",stop),payload))
            if self.mode=="filelist":
                address=varints((j,))
                self.db.executemany(BYTE_APPEND,((f,address) for f in ids))
            elif seal:
                packets={f:varints(events) for f,events in self.incident.items()}
                newest=varints((j,))
                for f in ids:packets[f]=packets.get(f,b"")+newest
                self.db.executemany(BYTE_APPEND,packets.items())
            if fault:raise RuntimeError("injected rollback")
            self.db.commit()
        except BaseException:
            self.db.rollback();raise
        if self.mode=="sealed_list":
            if seal:self.tail.clear();self.incident.clear()
            else:self._retain(j,ids)
        self.next_id+=1;self.offset=0 if seal else stop
        return True

    def _fetch_events(self,ids):
        if not ids:return [],0
        # Lists are chronological because every prefix was appended in ascending order.
        requests={p:[j%BLOCK for j in group] for p,group in groupby(ids,key=lambda j:j//BLOCK)}
        pages=list(requests)
        found=[]
        calls=0
        for start in range(0,len(pages),400):
            group=pages[start:start+400]
            placeholders=",".join("?" for _ in group)
            sql="SELECT b,ends,body FROM slab WHERE b IN ("+placeholders+")"
            for p,ends,body in self.db.execute(sql,group):
                self.src_blobs+=2;self.src_rows+=1;self.src_bytes+=len(ends)+len(body)
                found.extend((member_slice(ends,body,pos),) for pos in requests[p])
            calls+=1
        return found,calls
