"""Generate physically serialized source-coordinate receipts without access to gold evidence."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

os.environ["TOKENIZERS_PARALLELISM"] = "false"
from tokenizers import Tokenizer

D = Path(__file__).resolve().parent
WORK = D.parents[1]
UP = WORK / "graph_memory_round22/packing_control"
CACHE = Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")
TOK = Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
BUDGETS = (512, 1024, 2048)
FORMATS = ("bare", "short", "full", "merged", "space")
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    b = p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix == ".gz" else b)
def write(p, obj):
    raw = (json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False) + "\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix == ".gz" else raw)
def address_book():
    # One trace's integer namespace is fixed across all of its questions and all policies.
    tmp = D/"registry-stage.sqlite"
    if tmp.exists():
        raise FileExistsError(tmp)
    db = sqlite3.connect(tmp)
    try:
        db.execute("CREATE TABLE address(t TEXT,e INTEGER,eid TEXT,ptr TEXT,PRIMARY KEY(t,e),UNIQUE(t,eid,ptr)) WITHOUT ROWID")
        lock = read(UP/"no-next-forecast-seal.json")
        for name,digest in sorted(lock["files"].items()):
            p=UP/name
            assert sha(p)==digest
            for row in read(p):
                db.executemany("INSERT INTO address VALUES(?,?,?,?)",
                    [(row["t"],i,eid,ptr) for i,(eid,ptr) in enumerate(row["addresses"])])
        db.commit()
        assert db.execute("pragma integrity_check").fetchone()==("ok",)
        n,t=db.execute("SELECT count(*),count(distinct t) FROM address").fetchone()
        db.execute("vacuum")
    finally:
        db.close()
    assert t==1207
    final=D/"registry.sqlite"
    if final.exists():
        assert sha(tmp)==sha(final)
        tmp.unlink()
    else:
        tmp.replace(final)
    write(D/"inputs.json",{"fields":n,"trajectories":t,"registry_bytes":final.stat().st_size,"registry_sha":sha(final),
          "forecast":sha(UP/"no-next-forecast-seal.json"), "tokenizer":sha(TOK),"protocol":sha(D/"PROTOCOL_RU.md")})
def merge_ranges(raw,fields,ad,spaces):
    by=defaultdict(list)
    for rank,(e,l,h) in enumerate(raw):
        by[e].append((l,h,rank))
    runs=[]
    added=0
    for e,items in by.items():
        active=None
        for l,h,rank in sorted(items):
            if active is not None:
                gap=fields[ad[e][0]][active[2]:l] if 0<l-active[2]<=8 else ""
                if l<=active[2] or (spaces and gap and gap.isspace()):
                    added+=len(gap)
                    active[2]=max(active[2],h)
                    active[3]=min(active[3],rank)
                    continue
                runs.append(active)
            active=[e,l,h,rank]
        runs.append(active)
    return [r[:3] for r in sorted(runs,key=lambda r:r[3])],added
def encode(tok,ranges,ad,fields,fmt):
    spans=[]
    fragments=[]
    pos=0
    for i,(e,l,h) in enumerate(ranges):
        if i:
            fragments.append("\n");pos+=1
        eid,ptr=ad[e]
        if fmt=="bare": header=""
        elif fmt=="full": header=json.dumps([eid,ptr,l],separators=(",",":"),ensure_ascii=False)+" "
        else: header=f"[{e}:{l}] "
        body=fields[eid][l:h]
        assert len(body)==h-l and h>l
        fragments.extend((header,body))
        pos+=len(header)
        spans.append((pos,e,l,h))
        pos+=len(body)
    ctx="".join(fragments)
    assert len(ctx)==pos
    full=tok.encode(ctx,add_special_tokens=False)
    paid_by_budget={}
    for cap in BUDGETS:
        cut=pos
        paid=len(full.ids)
        if paid>cap:
            cut=full.offsets[cap][0]
            while True:
                paid=len(tok.encode(ctx[:cut],add_special_tokens=False).ids)
                if paid<=cap: break
                cut-=1
        shown=[]
        for start,e,l,h in spans:
            delivered=min(h-l,max(0,cut-start))
            if delivered:
                shown.append([e,l,l+delivered])
        paid_by_budget[str(cap)]=[paid,len(ctx[:cut].encode()),shown,hashlib.sha256(ctx[:cut].encode()).hexdigest()]
    return paid_by_budget
def shard(i):
    plan=read(D/"inputs.json")
    seal=read(UP/"no-next-forecast-seal.json")
    p=UP/f"no-next-decisions-{i}.json.gz"
    assert sha(p)==seal["files"][p.name] and sha(TOK)==plan["tokenizer"]
    tok=Tokenizer.from_file(str(TOK));assert tok.truncation is None
    db=sqlite3.connect((D/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    output=[]
    for row in read(p):
        t=row["t"]
        ad=[list(pair) for pair in db.execute("SELECT eid,ptr FROM address WHERE t=? ORDER BY e",(t,))]
        assert ad==row["addresses"] and len(ad)==len({a[0] for a in ad})
        fields=read(CACHE/f"{i}-{t}.json.gz")["fields"]
        for q,picks in row["picks"].items():
            result={}
            for arm,ids in picks.items():
                raw=[row["used"][k][:3] for k in ids]
                for fmt in FORMATS:
                    intervals,added=(merge_ranges(raw,fields,ad,fmt=="space") if fmt in ("merged","space") else (raw,0))
                    result[f"{arm}/{fmt}"]={"added_ws":added,"count":len(intervals),"paid":encode(tok,intervals,ad,fields,fmt)}
            output.append({"q":q,"t":t,"arms":result})
    db.close()
    dest=D/f"receipts-{i}.json.gz"
    write(dest,output)
    print("shard",i,len(output),flush=True)
    return dest.name,sha(dest)
def main():
    address_book()
    with ProcessPoolExecutor(2) as ex:
        parts=dict(ex.map(shard,range(8)))
    write(D/"receipt-lock.json",{"inputs":sha(D/"inputs.json"),"code":sha(Path(__file__)),"files":parts})
if __name__=="__main__":
    main()
