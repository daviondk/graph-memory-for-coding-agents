"""Replay two observed outgoing-support changes on the same time-masked candidate snapshot."""
from collections import defaultdict
from contextlib import closing
from hashlib import sha256
from itertools import combinations
from pathlib import Path
import gzip
import json
import sqlite3
import struct
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]
sys.path.insert(0,str(BASE/"graph_memory_round47/joint_packets"))
from bank import SCALE, Snapshot, build, choose, library
FIXTURE=HERE.parent/"observed_join/projection.json.gz"
DB=BASE/"graph_memory_round47/paper_demo/apps/trace/runtime/reader.sqlite"

def save(name,obj):
    data=(json.dumps(obj,separators=(",",":"),sort_keys=True)+"\n").encode()
    (HERE/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)
def packet_ids(binary):
    return [item for item, in struct.iter_unpack("<H",binary)]
def value(count,cap):
    return min(count,cap)*(SCALE//16)
def replay(db, lib, q, info):
    visibility=dict(info["sources"])
    origins={s:(int(pos),kind) for s,pos,kind in db.execute("SELECT source,position,role FROM origin WHERE q=?",(q,))}
    assert set(origins)==set(visibility)
    refs=defaultdict(set)
    for i,s in db.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):refs[i].add(s)
    prods=info["producers"]
    indices={p[0]:i for i,p in enumerate(prods) if p[0] in origins}
    assert all(origins[s][1]=="tool_output" for s in indices)
    items=[]
    for i,key,cost in db.execute("SELECT id,node_hash,tokens FROM node WHERE q=?",(q,)):
        if not refs[i]:continue
        fields=refs[i]
        items.append((max(visibility[s] for s in fields), -max(origins[s][0] for s in fields),
                      -min(origins[s][0] for s in fields),key,i,cost,tuple(sorted(indices[s] for s in fields if s in indices))))
    balance=[0]*len(prods);unit_count=db.execute("SELECT count(*) FROM node WHERE q=?",(q,)).fetchone()[0]
    events=[];excluded=0
    for step,frame in enumerate(info["steps"],1):
        _,message,deltas,*_=frame
        changed={i:b for i,a,b in deltas}
        assert all(balance[i]==a and b!=a and b>=0 for i,a,b in deltas)
        if len(changed)>=2:
            active=sorted((row for row in items if row[0]<=step),key=lambda row:row[1:4])
            owners={a for row in active for a in row[-1]}
            eligible=sorted(owners&set(changed))
            excluded+=len(changed)*(len(changed)-1)//2-len(eligible)*(len(eligible)-1)//2
            for cap in (1,4):
                rows=[];attached={}
                for rank,(_,_,_,key,i,cost,producers) in enumerate(active,1):
                    score=(SCALE+rank//2)//rank+sum(value(balance[a],cap) for a in producers)
                    rows.append((i,cost,score));attached[i]=set(producers)
                snap=Snapshot(rows)
                for a,b in combinations(eligible,2):
                    marks=[int(a in attached[i])+2*int(b in attached[i]) for i in snap.ids]
                    x=value(changed[a],cap)-value(balance[a],cap)
                    y=value(changed[b],cap)-value(balance[b],cap)
                    bank,_=build(lib,snap,marks)
                    direct=snap.native(lib,marks)
                    checks=[]
                    for dx,dy in [(0,0),(x,0),(0,y),(x,y)]:
                        result=choose(bank,dx,dy)
                        assert direct(dx,dy)==result
                        checks.append(packet_ids(result))
                    events.append(dict(step=step,group_end=message,a=a,b=b,cap=cap,x=x,y=y,
                                count=len(active),total_cost=sum(i[1] for i in rows),prefix=len(snap.head),
                                before=checks[0],first=checks[1],second=checks[2],after=checks[3]))
        for i,after in changed.items():balance[i]=after
    return dict(groups=len(info["steps"]),source_rows=len(origins),candidate_rows=unit_count,items_with_sources=len(items),
                excluded_pair_visits=excluded,events=events)
def main():
    fixture=json.loads(gzip.decompress(FIXTURE.read_bytes()))
    lib=library()
    with closing(sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True)) as db:
        out={q:replay(db,lib,q,info) for q,info in sorted(fixture["queries"].items())}
    save("packets.json.gz",out)
    save("inputs.json",{k:sha256(p.read_bytes()).hexdigest() for k,p in
         [("fixture",FIXTURE),("reader",DB),("protocol",HERE/"PROTOCOL_RU.md"),
          ("native",BASE/"graph_memory_round47/joint_packets/kernels.cpp")]})
    print(len(out),sum(len(r['events']) for r in out.values()))
if __name__=="__main__": main()
