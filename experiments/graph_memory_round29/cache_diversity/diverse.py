"""Test diversity decoders at equal K, accounting for counterfactual trace availability."""
from pathlib import Path
import sqlite3
import sys
import numpy as np
D=Path(__file__).resolve().parent;ROOT=D.parent
sys.path.insert(0,str(ROOT/"multi_retraction"))
from multiban_design import PRIVATE,arrays,read,save,sha,pack
from store import state
from measure import better,scan_window
POLICIES=("raw","coord","text","nms30","nms50","nms80","pareto")
BLIND=Path("D:/CodexResearch/x20-r26-squad-qa/blind-input.json.gz")
SCHEMA="(q INTEGER, rank INTEGER, score REAL, ord INTEGER, lo INTEGER, hi INTEGER, PRIMARY KEY(q,rank)) WITHOUT ROWID"

def prep():
    p,cases,old,logs,base=state()
    plan={"prior":sha(ROOT/"pareto_cache/manifest.json"),"gold":sha(ROOT/"multi_retraction/measurement-seal.json"),
        "protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),"source_text":sha(BLIND),"modes":list(POLICIES),"K":[8,64],"primary_iou":0.5}
    f=D/"plan.json"
    if f.exists():assert read(f)==plan
    else:save(f,plan)
    storage=PRIVATE/"diversity"/sha(f);storage.mkdir(parents=True,exist_ok=True)
    return p,cases,old,logs,base,storage

def surface(doc,l,h):return " ".join(doc[int(l):int(h)].split())

def nms(lo,hi,limit,t):
    kept=[]
    for i in range(len(lo)):
        l,h=lo[i],hi[i]
        for j in kept:
            overlap=max(0,min(h,hi[j])-max(l,lo[j]))
            union=h-l+hi[j]-lo[j]-overlap
            if 100*overlap>t*union:break
        else:
            kept.append(i)
            if len(kept)==limit:break
    return kept

def choose(tab,vs,doc):
    s,o,l,h=tab;l=l.tolist();h=h.tolist()
    picks={"raw":list(range(64)),"pareto":vs[:64]}
    for name in ("coord","text"):
        seen=set();unique=[]
        for i,(a,b) in enumerate(zip(l,h)):
            key=(a,b) if name=="coord" else surface(doc,a,b)
            if key in seen:continue
            seen.add(key);unique.append(i)
            if len(unique)==64:break
        picks[name]=unique
    for t in (30,50,80):picks["nms"+str(t)]=nms(l,h,64,t)
    assert all(len(x)==64 for x in picks.values())
    return picks

def make():
    p,cases,old,logs,base,storage=prep()
    if (D/"cache-seal.json").exists():return
    full=sqlite3.connect(old/"full.sqlite");pa=sqlite3.connect(base/"pareto.sqlite");docs=read(BLIND)["docs"]
    keys=[(mode,k) for mode in POLICIES for k in (8,64)]
    con={}
    for mode,k in keys:
        path=storage/(mode+str(k)+".sqlite")
        if path.exists():raise FileExistsError(path)
        db=sqlite3.connect(path);db.execute("CREATE TABLE r "+SCHEMA);db.execute("CREATE TABLE boundary(q INTEGER PRIMARY KEY, omitted_rank INTEGER)");con[mode,k]=db
    table={}
    for ix,q in enumerate(p["qids"]):
        tab=arrays(full,ix);s,o,l,h=tab;rank={int(x):i for i,x in enumerate(o)}
        vs=[rank[x[0]] for x in pa.execute("SELECT ord FROM r WHERE q=? ORDER BY score DESC,ord",(ix,))]
        picks=choose(tab,vs,docs[cases[q]["title"]]);table[q]={}
        for mode,k in keys:
            ids=picks[mode][:k];keep=set(ids);threshold=next((r for r in vs if r not in keep),len(o));name=mode+str(k)
            db=con[mode,k]
            db.executemany("INSERT INTO r VALUES (?,?,?,?,?,?)",((ix,i,float(s[i]),int(o[i]),int(l[i]),int(h[i])) for i in ids))
            db.execute("INSERT INTO boundary VALUES (?,?)",(ix,threshold))
            table[q][name]={"selected_ranks":ids,"first_unrepresented_possible_winner":threshold}
    full.close();pa.close()
    for db in con.values():db.commit();db.close()
    save(D/"selected.json.gz",table)
    save(D/"cache-seal.json",{"plan":sha(D/"plan.json"),"picks":sha(D/"selected.json.gz"),"sqlite":{
        name:{"bytes":f.stat().st_size,"sha":sha(f)} for f in sorted(storage.glob("*.sqlite")) for name in [f.stem]}})

def main():
    p,cases,old,logs,base,storage=prep();make();parent=read(ROOT/"multi_retraction/predictions.json.gz")
    docs=read(BLIND)["docs"];sc=read(D/"cache-seal.json")["sqlite"]
    cache={name:sqlite3.connect(storage/(name+".sqlite")) for name in sc}
    db=sqlite3.connect(logs/"bounds.sqlite");db.execute("ATTACH DATABASE ? AS z",(str(logs/"zip.sqlite"),))
    allrows={};strict=0
    for ix,q in enumerate(p["qids"]):
        allrows[q]={};doc=docs[cases[q]["title"]]
        tables={n:cc.execute("SELECT rank,score,ord,lo,hi FROM r WHERE q=? ORDER BY rank",(ix,)).fetchall() for n,cc in cache.items()}
        bounds={n:cc.execute("SELECT omitted_rank FROM boundary WHERE q=?",(ix,)).fetchone()[0] for n,cc in cache.items()}
        window_bounds=db.execute("SELECT score,ord,lo,hi,w FROM r WHERE q=? ORDER BY score DESC,ord",(ix,)).fetchall()
        for cond,item in parent[q].items():
            gold=item["answer"];bans=item["ban"];row={}
            for name in sc:
                first=next((r for r in tables[name] if all(r[4]<=l or r[3]>=h for l,h in bans)),None)
                found=tuple(first[1:]) if first else None;oracle=bool(found and pack(found)==pack(gold))
                bytext=bool(found and gold and surface(doc,found[2],found[3])==surface(doc,gold[2],gold[3]))
                certified=bool(first and first[0]<bounds[name]);assert not certified or oracle
                wrong=int(bool(first and not oracle));windows=0;bytes_read=0
                if not certified:
                    for s,o,l,h,w in window_bounds:
                        upper=(s,o,l,h)
                        if not better(upper,found):break
                        if all(h<=a or l>=b for a,b in bans):v=upper
                        else:
                            buf=db.execute("SELECT b FROM z.r WHERE q=? AND w=?",(ix,w)).fetchone()[0]
                            bytes_read+=len(buf);windows+=1;v=scan_window(buf,w,bans)
                        if better(v,found):found=v
                assert pack(found)==pack(gold),(name,q,cond,first,gold,found)
                strict+=1
                row[name]=[int(oracle),int(certified),wrong,int(bytext),windows,bytes_read]
            if "-" in cond:allrows[q][cond]=row
        if (ix+1)%16==0:print("checked",ix+1,flush=True)
    for c in cache.values():c.close()
    db.close();save(D/"rows.json.gz",allrows);save(D/"result-seal.json",{"cache":sha(D/"cache-seal.json"),"rows":sha(D/"rows.json.gz"),"strict":strict,
        "fields":["exact_oracle_hit","certified_hit","wrong_nonempty_naive_return","correct_surface_if_nonempty","recomputed_windows","blob_bytes"]})
if __name__=="__main__":main()
