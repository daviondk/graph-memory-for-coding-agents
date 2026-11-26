"""Persist exact certificates and strong compact baselines in independent SQLite files."""
from collections import defaultdict
from itertools import combinations
from math import comb
from pathlib import Path
import sqlite3,sys,time
HERE=Path(__file__).resolve().parent
PAIR=HERE.parent/"support_pairs";sys.path.insert(0,str(PAIR))
from prepare import PRIVATE,get,put,sha
from families import failures
DBROOT=PRIVATE/"stores"
MODES=("rows","full","tree","basis","raw","lookup")
def code(a,b):return (a<<4)|b
def mask(edge):return (1<<(edge>>4))|(1<<(edge&15))
def ordered_bans(n):
    return [bits for k in range(min(n,2)+1) for bits in combinations(range(n),k)]
def direct_address(n,removed):
    if not removed:return 0
    if len(removed)==1:return 1+removed[0]
    a,b=removed
    return 1+n+a*(2*n-a-1)//2+(b-a-1)
def scans(payload,banned):
    for e in payload:
        if not mask(e)&banned:return e
    return 255
def build():
    ranks=get(PAIR/"rankings.json.gz");cached=get(PAIR/"cache-measurements.json.gz")
    src=get(PAIR/"measurement-seal.json");assert sha(PAIR/"cache-measurements.json.gz")==src["measurements"]
    lock={"rankings":sha(PAIR/"rankings.json.gz"),"cache":src["measurements"],"protocol":sha(HERE/"PROTOCOL_RU.md"),"extension":sha(HERE/"OUTSIDE_RU.md"),"code":sha(Path(__file__))}
    put(HERE/"plan.json",lock);directory=DBROOT/sha(HERE/"plan.json");directory.mkdir(parents=True,exist_ok=True)
    logical=defaultdict(int);rows=defaultdict(int)
    connections={}
    for mode in MODES:
        path=directory/(mode+".sqlite")
        if path.exists():raise FileExistsError(path)
        db=sqlite3.connect(path)
        if mode=="rows":
            db.execute("create table candidates(q integer, r integer, pair integer, dependency integer, primary key(q,r)) without rowid")
        else:db.execute("create table candidates(q integer primary key, payload blob not null)")
        connections[mode]=db
    times=defaultdict(int);keys=sorted(ranks)
    for ix,k in enumerate(keys):
        rec=ranks[k];n=len(rec["order"]);raw=bytes(code(*p) for p in rec["pairs"]["joint"])
        cap=cached[k]["joint"]["2"]
        with_ids={"full":raw,"tree":bytes(raw[i] for i in cap["tree"]),"basis":bytes(raw[i] for i in cap["linear"]),"raw":raw[:6]}
        bans=ordered_bans(n);assert all(direct_address(n,b)==i for i,b in enumerate(bans))
        t=time.perf_counter_ns();with_ids["lookup"]=bytes(scans(raw,sum(1<<i for i in b)) for b in bans);times["lookup_compute"]+=time.perf_counter_ns()-t
        for m,enc in with_ids.items():
            t=time.perf_counter_ns();connections[m].execute("insert into candidates values (?,?)",(ix,enc));times[m]+=time.perf_counter_ns()-t
            logical[m]+=len(enc);rows[m]+=1
        t=time.perf_counter_ns();connections["rows"].executemany("insert into candidates values (?,?,?,?)",((ix,r,v,mask(v)) for r,v in enumerate(raw)))
        times["rows"]+=time.perf_counter_ns()-t;rows["rows"]+=len(raw)
    checks={}
    for mode,db in connections.items():
        t=time.perf_counter_ns();db.commit();db.execute("vacuum");db.close();times[mode]+=time.perf_counter_ns()-t
        path=directory/(mode+".sqlite")
        with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as rd:assert rd.execute("pragma integrity_check").fetchone()==("ok",)
        checks[mode]={"file_bytes":path.stat().st_size,"sha":sha(path),"dataset_rows":rows[mode],"payload_bytes":logical.get(mode),"write_commit_vacuum_ns":times[mode]}
    put(HERE/"build.json",{"stores":checks,"database_directory_hash":directory.name,"lookup_compute_ns":times["lookup_compute"],"questions":len(keys)})
def open_db(dir,mode):
    return sqlite3.connect((dir/(mode+".sqlite")).as_uri()+"?immutable=1&mode=ro",uri=True)
class Store:
    def __init__(self,directory):
        self.db={m:open_db(directory,m) for m in MODES}
    def close(self):
        for db in self.db.values():db.close()
    def query(self,method,ix,n,removed):
        bits=sum(1<<i for i in removed)
        if n-len(removed)<2:return 255,0,0,"empty"
        if method=="rows":
            row=self.db["rows"].execute("select pair from candidates where q=? and (dependency & ?)=0 order by r limit 1",(ix,bits)).fetchone()
            return (row[0] if row is not None else 255),1,1 if row else 0,"sql"
        mode="tree" if method.startswith("tree_") else method
        def load(m):return self.db[m].execute("select payload from candidates where q=?",(ix,)).fetchone()[0]
        if len(removed)>2 and mode in ("tree","basis","lookup") and method!="tree_certificate":
            payload=load("full");return scans(payload,bits),1,len(payload),"direct_fallback"
        v=load(mode);count=1;wire=len(v)
        if mode=="lookup":return v[direct_address(n,removed)],count,wire,"lookup"
        if method=="tree_certificate" and len(removed)>2:
            for k in range(3):
                for small in combinations(removed,k):
                    e=scans(v,sum(1<<i for i in small))
                    if e==255 or not mask(e)&bits:return e,count,wire,"certified"
        else:
            e=scans(v,bits)
            if mode!="raw" or e!=255:return e,count,wire,"cache"
        full=load("full");return scans(full,bits),count+1,wire+len(full),"fallback"
if __name__=="__main__":build()
