"""Persist one compact address header per old snapshot and recover routing from durable SQLite state."""
from features import D,P,V,S,sha,get,put,h,vector
from struct import pack,iter_unpack
from pathlib import Path
from time import perf_counter_ns
from tempfile import TemporaryDirectory
from itertools import permutations
import sys,sqlite3
sys.path.insert(0,str(S))
from benchmark import cycles
from storage import initialize,transition,lookup,rows

def add_headers(db,items,history,meta,panel):
    pages=db.execute("PRAGMA page_count").fetchone()[0];start=perf_counter_ns()
    db.execute("CREATE TABLE stats(e INTEGER PRIMARY KEY,prev INTEGER NOT NULL,nviews INTEGER NOT NULL,nedits INTEGER NOT NULL,addresses BLOB NOT NULL)")
    db.execute("BEGIN");total=0
    for i,q in enumerate(panel):
        addrs=b"".join(pack(">I",n) for n,_ in items[i]["base"])
        age,nv,ne=history[q];assert meta[q]["prev"]+age==meta[q]["edit"]
        db.execute("INSERT INTO stats VALUES(?,?,?,?,?)",(i,meta[q]["prev"],nv,ne,addrs));total+=len(addrs)
    db.commit();db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    return dict(prep_wall_ns=perf_counter_ns()-start,address_bytes=total,rows=len(items),
                additional_pages=db.execute("PRAGMA page_count").fetchone()[0]-pages)
def choose(db,e,item,current,model):
    prev,nv,ne,blob=db.execute("SELECT prev,nviews,nedits,addresses FROM stats WHERE e=?",(e,)).fetchone()
    vec=vector([n for n, in iter_unpack(">I",blob)],item["receipt"],item["start"],item["end"],item["delta"],current-prev,nv,ne)
    score=model["intercept"]+sum(a*b for a,b in zip(vec,model["coef"]))
    return "L" if score>0 else "A"
def lookuproute(db,e,item):
    plan="L" if db.execute("SELECT 1 FROM v WHERE e=?",(e,)).fetchone() else "A"
    return lookup(db,plan,e,item)
def evaluate():
    fit=get(D/"fit-seal.json");assert fit["decisions"]==sha(D/"decisions.json.gz") and fit["model"]==sha(D/"models.json")
    selected=get(D/"decisions.json.gz");model=get(D/"models.json");hist=get(D/"history.json.gz")
    meta={r["q"]:r for r in get(P/"followup.json.gz")};prefix=get(P/"prefixes.json.gz")
    panel=get(P/"physical-plan.json")["panel"];items={i:{**prefix[q],"base":rows(prefix[q]["base"]),"receipt":dict(rows(prefix[q]["receipt"]))} for i,q in enumerate(panel)}
    # Eager-length and lazy-length expected answer is generated only for checking, outside timing.
    def ref(item):
        eligible={}
        if item["start"] is not None:
            for n,s in item["base"]:
                if item["start"]<=n<=item["end"]:continue
                d=n if n<item["start"] else n+item["delta"]
                if d not in item["receipt"]:eligible[d]=s
        sort=sorted(eligible,key=lambda n:h("R37-128|"+item["path"]+"|"+str(n)))[:128-len(item["receipt"])]
        return sorted((dict((n,eligible[n]) for n in sort)|item["receipt"]).items())
    expected={i:ref(v) for i,v in items.items()}
    reps={q:[] for q in panel};met=[];order=list(permutations("ALH"))
    with TemporaryDirectory(dir=D,prefix="route_") as td:
        for rep in range(-1,6):
            fs={m:Path(td)/(m+str(rep)+".db") for m in "ALH"}
            db={m:initialize(fs[m],"L" if m=="H" else m,items) for m in "ALH"}
            met.append(add_headers(db["H"],items,hist,meta,panel))
            for i,q in enumerate(panel):
                sets={};item=items[i];frozen=model[meta[q]["repo"]]["ridge"];event_idx=meta[q]["edit"]
                for m in order[(max(rep,0)+int(h("H-route-order|"+q)[:12],16))%6]:
                    con=db[m];w=perf_counter_ns();c=cycles()
                    k=choose(con,i,item,event_idx,frozen) if m=="H" else m
                    writes,pre_rows,_=transition(con,k,i,item)
                    cw=cycles()-c;ww=perf_counter_ns()-w
                    if m=="H":assert k==selected[q]["H"]
                    n=meta[q]["strict"]["reads"]
                    if n:
                        w=perf_counter_ns();c=cycles()
                        if m=="H":got=[lookuproute(con,i,item) for _ in range(n)]
                        else:got=[lookup(con,m,i,item) for _ in range(n)]
                        cr=cycles()-c;wr=perf_counter_ns()-w
                        assert all(x==expected[i] for x,_ in got)
                    else:cr=wr=0
                    sets[m]=[ww,wr,cw,cr,writes,pre_rows,n]
                if rep>=0:reps[q].append(sets)
            # A separate connection has no per-episode decision map. After warmup validate all, including zeros.
            for con in db.values():con.close()
            if rep==-1:
                fresh=sqlite3.connect(fs["H"])
                for i,item in items.items():assert lookuproute(fresh,i,item)[0]==expected[i]
                fresh.close()
    put(D/"live-seal.json",dict(samples=put(D/"live-timings.json.gz",reps),fit=sha(D/"fit-seal.json"),header_preparation=met,
        sqlite=sqlite3.sqlite_version,code=sha(Path(__file__)),shared_reader_verified=len(panel)))
if __name__=="__main__":evaluate()
