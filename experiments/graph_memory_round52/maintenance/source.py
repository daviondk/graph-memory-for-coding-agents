"""Rebuild the prefix workload from public-text projections and verify all terminal edge bits."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sqlite3

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[1]/"graph_memory_round51"/"policy_replay"/"rank.sqlite"
SCRATCH=Path("D:/CodexResearch/x20-r52-maintenance")
PANELS=("adaptive_address","gate_confirmation","hotpot","confirm")
SALT="r52-witness-io-v1"
def sha(data):
    return hashlib.sha256(data).hexdigest()
def write(name,data):
    raw=json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    if name.endswith(".gz"):
        raw=gzip.compress(raw,mtime=0)
    (ROOT/name).write_bytes(raw)
def read(name):
    v=(ROOT/name).read_bytes()
    if name.endswith(".gz"):
        v=gzip.decompress(v)
    return json.loads(v)
def words(s):
    return re.findall(r"[^\W_]+",s.lower())
def prepare():
    db=sqlite3.connect(SOURCE.as_uri()+"?immutable=1&mode=ro",uri=True)
    weights=db.execute("SELECT w0,w1,w2,w3,w4 FROM coef WHERE policy='graph'").fetchone()
    assert weights[-1]>0
    data=[]
    for panel,name,fragment,label in db.execute("SELECT panel,q,fragment,first_title FROM question ORDER BY panel,q"):
        tokens=words(fragment)
        cuts=max(1,math.ceil(len(tokens)/16))
        candidates=[]
        for i,title,cos,qr,sr,dr,edge in db.execute("SELECT cid,title,cos,qr,sr,dr,edge FROM candidate WHERE panel=? AND q=? ORDER BY dr",(panel,name)):
            seq=words(title);end=None
            if sum(map(len,seq))>=3:
                end=next((k+len(seq) for k in range(len(tokens)-len(seq)+1) if tokens[k:k+len(seq)]==seq),None)
            assert (end is not None)==bool(edge)
            b=weights[0]*cos+weights[1]/(1.+qr)+weights[2]/(1.+sr)+weights[3]/(1.+dr)
            candidates.append([i,dr,b,b+weights[-1],None if end is None else math.ceil(end/16)])
        terminal=min(candidates,key=lambda v:(-(v[3] if v[4] is not None else v[2]),v[1],v[0]))[0]
        sealed=db.execute("""SELECT cid FROM candidate JOIN coef ON policy='graph' WHERE panel=? AND q=?
           ORDER BY w0*cos+w1/(1.+qr)+w2/(1.+sr)+w3/(1.+dr)+w4*edge DESC,dr LIMIT 1""",(panel,name)).fetchone()[0]
        assert terminal==sealed
        data.append(dict(panel=panel,q=name,digest=sha((label+"\0"+fragment).encode()),tokens=len(tokens),
                         cuts=cuts,candidates=candidates,terminal=terminal))
    db.close()
    return data
def blocks(data):
    panels={p:sorted((i for i,e in enumerate(data) if e["panel"]==p),key=lambda i:sha((SALT+"|"+p+"|"+data[i]["q"]).encode()))[:256] for p in PANELS}
    result=[]
    for index in range(32):
        group=[q for p in PANELS for q in panels[p][8*index:8*(index+1)]]
        random.Random(528810+index).shuffle(group);result.append(group)
    return result
def winner(candidates,cut):
    return min(candidates,key=lambda v:(-(v[3] if v[4] is not None and v[4]<=cut else v[2]),v[1],v[0]))[0]
def schedule(data,bs):
    groups=[]
    for ids in bs:
        events=[]
        for q in ids:
            e=data[q];rng=random.Random(SALT+"|asof|"+e["panel"]+"|"+e["q"])
            answers=[winner(e["candidates"],k) for k in range(1+e["cuts"])]
            for k in range(1,1+e["cuts"]):
                added=tuple(v[0] for v in e["candidates"] if v[4]==k)
                old=tuple(rng.randrange(k) if ix%2==0 else k for ix in range(8))
                events.append((q,k,added,tuple((t,answers[t]) for t in old),answers[k]))
        groups.append(events)
    return groups
if __name__=="__main__":
    data=prepare()
    write("workload.json.gz",data)
    write("registration.json",dict(protocol=sha((ROOT/"PROTOCOL_RU.md").read_bytes()),input=sha(SOURCE.read_bytes()),
          source=sha((ROOT/"source.py").read_bytes()),workload=sha((ROOT/"workload.json.gz").read_bytes()),
          schedule=sha(json.dumps(schedule(data,blocks(data)),separators=(",",":")).encode()),seed=528810,n=len(data)))

