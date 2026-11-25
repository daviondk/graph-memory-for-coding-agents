"""Read and project coordinate-only records for the frozen inspection database."""
from collections import defaultdict
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent
DB=ROOT/"inspection.sqlite"
OPEN_SQL=("SELECT field_no, a, b, paid_wp FROM observed_open\n"
          "WHERE case_id = ? AND field_no = ? AND a = ?")
FORMATS=("short","receiver","sender")
POLICIES=("bm25","first_positive")
def connect():
    db=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    db.execute("PRAGMA query_only=ON")
    return db
def cases(db):
    group={"additional":0,"bm25":1,"no_read":2,"duplicate":3,"hash":4}
    raw=[dict(id=k,mode=m,selection=s) for k,m,s in db.execute("SELECT id,mode,reason FROM sample")]
    return sorted(raw,key=lambda v:(group[v["selection"]],v["id"]))
def pooled(spans):
    out=[]
    for e,a,b in sorted(spans):
        if out and out[-1][0]==e and out[-1][2]>=a:out[-1][2]=max(out[-1][2],b)
        else:out.append([e,a,b])
    return out
def view(db,sample,fmt,policy):
    if fmt not in FORMATS or policy not in POLICIES:raise ValueError("Invalid preset")
    rec=db.execute("SELECT wire_wp,inside_wp,wire_bytes FROM memory WHERE case_id=? AND fmt=?",(sample,fmt)).fetchone()
    if rec is None:raise ValueError("Unknown case")
    wire,internal,wire_bytes=rec
    field,a,estimated,rank,origin=db.execute("SELECT field_no,a,predicted,rank,origin FROM decision WHERE case_id=? AND fmt=? AND policy=?",(sample,fmt,policy)).fetchone()
    found=None;params=None
    if field is not None:
        params=[sample,field,a];found=db.execute(OPEN_SQL,params).fetchone()
        if not found:raise ValueError("Broken read receipt")
    get=lambda kind,f:[list(p) for p in db.execute("SELECT field_no,a,b FROM source_span WHERE case_id=? AND kind=? AND fmt=? ORDER BY ordinal",(sample,kind,f))]
    gold=pooled(get("gold",""));oldraw=get("memory",fmt);old=pooled(oldraw);opened=[list(found[:3])] if found else []
    fields=defaultdict(lambda:[[],[],[]])
    for i,spans in enumerate((gold,old,opened)):
        for e,l,h in spans:
            if h>l:fields[e][i].append((l,h))
    total=initial=gain=ret=fresh=memory_chars=0;components=[]
    for e,buckets in sorted(fields.items()):
        cuts=sorted({v for intervals in buckets for p in intervals for v in p})
        for l,h in zip(cuts,cuts[1:]):
            g,m,o=(any(a<=l and h<=b for a,b in ss) for ss in buckets)
            length=h-l
            total+=length*g;initial+=length*(g and m);gain+=length*(g and o and not m)
            ret+=length*o;fresh+=length*(o and not m);memory_chars+=length*m
            if g:
                status="memory" if m else "added" if o else "missing"
                if components and components[-1][0]==e and components[-1][2]==l and components[-1][3]==status:components[-1][2]=h
                else:components.append([e,l,h,status])
    paid=found[3] if found else 0
    return dict(case=sample,format=fmt,policy=policy,gold=gold,components=components,memory=oldraw,source=opened,
                sql=OPEN_SQL if found else None,params=params,origin=origin,rank=rank,estimated_new_chars=estimated,
                metrics=dict(gold=total,memory_gold=initial,new_gold=gain,missing=total-initial-gain,
                             returned=ret,added_source=fresh,memory_chars=memory_chars,wire_wp=wire,wire_bytes=wire_bytes,
                             inside_wp=internal,open_wp=paid,total_wp=wire+paid,initial_full=initial==total,full=initial+gain==total))
