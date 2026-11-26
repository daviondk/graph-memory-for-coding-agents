"""One tagged BLOB per snapshot and ahead-of-time feature tables. Frozen H decisions."""
from inputs import *
import engine
from struct import Struct,pack,unpack
from itertools import chain
from math import log1p
from time import perf_counter_ns
TABLE=Struct("<257d")
def build_tables():
    models=get(H/"models.json");start=perf_counter_ns();out=bytearray()
    logs=tuple(log1p(i) for i in range(257))
    for r in sorted(models):
        for b in models[r]["ridge"]["coef"]:out.extend(TABLE.pack(*(b*v for v in logs)))
    (D/"coefficients.bin").write_bytes(out)
    return dict(time_ns=perf_counter_ns()-start,bytes=len(out),sha=sha(D/"coefficients.bin"))
def load_tables(models):
    raw=(D/"coefficients.bin").read_bytes();out={};off=0
    for r in sorted(models):
        m=models[r]["ridge"];beta=m["coef"];tables=tuple(TABLE.unpack_from(raw,off+j*TABLE.size) for j in range(len(beta)))
        out[r]=(m["intercept"],beta,tables);off+=len(beta)*TABLE.size
    assert off==len(raw)
    return out

def ingest(db,mode,e,pairs,marker,prev):
    if mode!="H":return engine.ingest(db,mode,e,pairs,marker,prev)
    base={n:bytes.fromhex(s) for n,s in pairs};nums=tuple(base);hist=(prev,marker.count("v"),marker.count("e"))
    items=iter(base.items());n,s=next(items,(0,b""));prefix=(e,n,s+pack(">III",*hist))
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany("INSERT INTO f VALUES(?,?,?)",chain((prefix,),((e,j,v) for j,v in items)))
        db.commit()
    except Exception:
        db.rollback();raise
    return base,nums,hist

def edit(db,mode,model,e,old,x):
    if mode!="H" or old is not None:return engine.edit(db,mode,model,e,old,x)
    raw=db.execute("SELECT n,s FROM f WHERE e=? ORDER BY n",(e,)).fetchall()
    n,s=raw[0];hist=unpack(">III",s[-12:]);assert n==0 or len(s)==44
    if n:raw[0]=(n,s[:32]);base=dict(raw)
    else:base=dict(raw[1:])
    k,state,_,_=engine.edit(db,mode,model,e,(base,tuple(base),hist),x)
    return k,state,1,len(raw)

def answer(db,mode,e,path,state):
    if mode!="H" or state is not None:return engine.answer(db,mode,e,path,state)
    records=db.execute(engine.QUERY,(e,)).fetchall();base={};receipt={};meta=None
    for tag,n,z,d,s in records:
        if tag==0:base[n]=s if len(s)==32 else s[:32]
        elif tag==1:receipt[n]=s
        else:meta=(n,z,d)
    goal=base if meta is None else engine.material(path,base,receipt,*meta)
    return tuple(sorted(goal.items())),1,len(records)
