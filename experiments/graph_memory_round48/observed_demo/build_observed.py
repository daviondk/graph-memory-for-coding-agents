"""Build anonymous, queryable cases directly from the recorded support transaction ledger."""
from pathlib import Path
from itertools import combinations
from collections import Counter,defaultdict
from contextlib import closing
from hashlib import sha256
import gzip,json,sqlite3,sys
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D/"apps/trace"))
from observed import calculate
def load(p):
    return json.loads(gzip.decompress(p.read_bytes()))
def build():
    upstream=load(D.parent/"observed_join/projection.json.gz")["queries"]
    full=load(D.parent/"support_updates/group-packets.json.gz")
    pairs=load(D.parent/"support_updates/packets.json.gz")
    reader=D/"apps/trace/runtime/reader.sqlite"
    dbpath=D/"apps/trace/runtime/observed.sqlite"
    if dbpath.exists():raise FileExistsError(dbpath)
    with closing(sqlite3.connect(reader.resolve().as_uri()+"?mode=ro",uri=True)) as db, closing(sqlite3.connect(dbpath)) as out:
        out.executescript("""CREATE TABLE event (q TEXT,step INTEGER,nodes TEXT,updates TEXT,PRIMARY KEY(q,step));
                          CREATE TABLE chosen(q TEXT,step INTEGER,cap INTEGER,subset TEXT,ids TEXT,PRIMARY KEY(q,step,cap,subset)) WITHOUT ROWID;""")
        n=0
        for q,info in sorted(upstream.items()):
            vis=dict(info["sources"]);pos=dict(db.execute("SELECT source,position FROM origin WHERE q=?",(q,)))
            owners={p[0]:i for i,p in enumerate(info["producers"])}
            fields=defaultdict(set)
            for i,s in db.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):fields[i].add(s)
            raw=list(db.execute("SELECT id,node_hash,tokens FROM node WHERE q=?",(q,)))
            old=Counter();group={(r["step"],r["cap"]):r for r in full[q]}
            pair={(e["step"],e["cap"],e["a"],e["b"]):e for e in pairs[q]["events"]}
            for step,(_,_,changes,*_) in enumerate(info["steps"],1):
                if len(changes)>=2:
                    active=[]
                    for i,key,cost in raw:
                        f=fields[i]
                        if not f or max(vis[s] for s in f)>step:continue
                        p=[pos[s] for s in f]
                        active.append(((-max(p),-min(p),key),[i,cost,[[owners[s],old[owners[s]]] for s in sorted(f) if s in owners]]))
                    nodes=[v for k,v in sorted(active)]
                    out.execute("INSERT INTO event VALUES(?,?,?,?)",(q,step,json.dumps(nodes),json.dumps(changes)))
                    changed=sorted({i for i,_,_ in changes})
                    options=[(),*((i,) for i in changed),*combinations(changed,2),tuple(changed)]
                    for cap in (1,4):
                        audit=group[step,cap]
                        for subset in dict.fromkeys(options):
                            ids=calculate(nodes,changes,cap,subset)
                            if not subset: assert ids==audit["base"]
                            if len(subset)==len(changed): assert ids==audit["after"]
                            if len(subset)==1: assert (ids==audit["base"])==(subset[0] in audit["single_same"])
                            if len(subset)==2:
                                assert ids==pair[step,cap,*subset]["after"]
                            key=",".join(map(str,subset))
                            out.execute("INSERT INTO chosen VALUES(?,?,?,?,?)",(q,step,cap,key,json.dumps(ids)))
                for i,a,b in changes:
                    assert old[i]==a;old[i]=b
        out.commit()
        print(out.execute("SELECT count(*) FROM event").fetchone(),out.execute("SELECT count(*) FROM chosen").fetchone())
if __name__=="__main__":build()
