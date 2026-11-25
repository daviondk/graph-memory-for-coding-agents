"""Compile exact incidence and dominance on the fixed, visible observation catalogue."""
from pathlib import Path
from time import perf_counter_ns as now
import sqlite3
import numpy as np
from inputs import D,DIV,PRIVATE,R,arrays,decode,read,save,sha,state

FIELDS="(q INTEGER,rank INTEGER,score REAL,ord INTEGER,lo INTEGER,hi INTEGER,mask INTEGER,PRIMARY KEY(q,rank)) WITHOUT ROWID"
def sources():
    p,cases,old,logs,base=state();plan=read(D/"plan.json")
    assert plan["protocol"]==sha(D/"PROTOCOL_RU.md") and read(D/"event-seal.json")["events"]==sha(D/"events.json.gz")
    dest=PRIVATE/"receipt"/sha(D/"plan.json");dest.mkdir(parents=True,exist_ok=True)
    return p,cases,old,logs,base,dest

def mask_vector(lo,hi,reg):
    assert len(reg)<=62
    masks=np.zeros(len(lo),np.uint64)
    for i,(l,h) in enumerate(reg):
        masks|=(((hi>l)&(lo<h)).astype(np.uint64)<<np.uint64(i))
    assert np.all(masks!=0)
    return masks

def build():
    p,cases,old,logs,base,dest=sources();plan=read(D/"plan.json");events=read(D/"events.json.gz")
    diversity=read(DIV/"selected.json.gz")
    if (D/"build-seal.json").exists():return
    original=sqlite3.connect(old/"full.sqlite");raw=sqlite3.connect(logs/"raw.sqlite")
    registry=sqlite3.connect(dest/"registry.sqlite");registry.execute("CREATE TABLE r(q INTEGER,i INTEGER,lo INTEGER,hi INTEGER,PRIMARY KEY(q,i),UNIQUE(q,lo,hi)) WITHOUT ROWID")
    db={}
    for m in plan["policies"]:
        for k in plan["sizes"]:
            path=dest/(m+str(k)+".sqlite")
            if path.exists():raise FileExistsError(path)
            con=sqlite3.connect(path);con.execute("CREATE TABLE r "+FIELDS)
            con.execute("CREATE TABLE cert(q INTEGER PRIMARY KEY, full_mask INTEGER, first_omitted_rank INTEGER, geometric_limit INTEGER)")
            db[m,k]=con
    info={}
    for ix,q in enumerate(p["qids"]):
        tab=arrays(original,ix);scores,orders,lo,hi=tab;reg=events[q]["registry"]
        registry.executemany("INSERT INTO r VALUES (?,?,?,?)",((ix,j,l,h) for j,(l,h) in enumerate(reg)))
        t=now();mask=mask_vector(lo,hi,reg);t_inc=now()-t;t=now()
        _,idx=np.unique(mask,return_index=True);groups=sorted(idx.tolist());mins=[];selected_masks=[]
        for i in groups:
            v=int(mask[i])
            if any(s&v==s for s in selected_masks):continue
            selected_masks.append(v);mins.append(i)
        t_sets=now()-t;t=now();tok=orders//30;wind=tok//384;starts=tok%384
        producer=np.empty(len(orders),np.int32)
        for wi,b in raw.execute("SELECT w,b FROM r WHERE q=? ORDER BY w",(ix,)):
            which=wind==wi;producer[which]=decode(b)[2][starts[which]]
        assert np.all(producer>=0)
        _,idx=np.unique(producer,return_index=True);prod=sorted(idx.tolist());t_producer=now()-t
        policy={"raw":list(range(64)),"nms30":diversity[q]["nms3064"]["selected_ranks"],"geometry":diversity[q]["pareto64"]["selected_ranks"],
                "producer":prod,"mask_group":groups,"mask_pareto":mins}
        row={"registry":len(reg),"source_n":len(orders),"distinct_masks":len(groups),"minimal_masks":len(mins),"producers":len(prod),
             "incidence_ns":t_inc,"group_and_pareto_ns":t_sets,"producer_ns":t_producer,"stores":{}}
        for (m,k),con in db.items():
            ids=policy[m][:k];cut=next((z for z in mins if z not in set(ids)),len(orders))
            name=m+str(k);geom=("pareto" if m=="geometry" else m)+str(k)
            glimit=diversity[q][geom]["first_unrepresented_possible_winner"] if m in ("raw","geometry","nms30") else -1
            data=((ix,i,float(scores[i]),int(orders[i]),int(lo[i]),int(hi[i]),int(mask[i])) for i in ids)
            con.executemany("INSERT INTO r VALUES (?,?,?,?,?,?,?)",data)
            con.execute("INSERT INTO cert VALUES (?,?,?,?)",(ix,int(cut==len(orders)),cut,glimit))
            row["stores"][name]={"kept":len(ids),"complete":cut==len(orders),"omitted":cut}
        info[q]=row
    for con in db.values():con.commit();con.close()
    registry.commit();registry.close();original.close();raw.close()
    save(D/"build-rows.json.gz",info);save(D/"build-seal.json",{"plan":sha(D/"plan.json"),"data":sha(D/"build-rows.json.gz"),"code":sha(Path(__file__)),
        "basis":sha(DIV/"manifest.json"),"files":{f.stem:{"bytes":f.stat().st_size,"sha":sha(f)} for f in sorted(dest.glob("*.sqlite"))}})
if __name__=="__main__":build()
