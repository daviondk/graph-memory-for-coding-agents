"""Enumerate feasible answers on genuine overlap between independently observed canonical lines."""
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
from time import perf_counter_ns as now
import os
import random
import sqlite3
from prepare import D,P,h,read,save,sha

def available():
    plan=read(D/"plan.json");base=P/sha(D/"plan.json");src=read(D/"source-seal.json")
    assert src["private_input"]==sha(base/"input.json.gz") and src["plan"]==sha(D/"plan.json")
    return plan,base,read(base/"input.json.gz")

def ranker(v,level,order):
    rows=v["line_producer_atom"];matches=v[level+"_score"]
    if level=="line":units=[(e,(a,)) for e,a in rows]
    else:units=[(j,tuple(sorted(set(atoms)))) for j,(msg,atoms) in enumerate(v["events"])]
    priority=sorted(range(len(units)),key=lambda i:(-matches[i] if order=="bm25" else 0,-units[i][0],i))
    return [units[i] for i in priority],priority

def make_masks(units,events,atoms):
    ownership=[0]*len(atoms)
    for j,(msg,indices) in enumerate(events):
        for a in indices:ownership[a]|=1<<j
    masks=[]
    for j,inds in units:
        val=0
        for i in inds:val|=ownership[i]
        assert val&(1<<j);masks.append(val)
    return masks

def selected(units,masks):
    def first(items):
        by={}
        for i,k in enumerate(items):by.setdefault(k,i)
        return list(by.values())
    producers=first([v[0] for v in units]);atoms=first([v[1] for v in units]);groups=first(masks)
    minimal=[];held=[]
    for i in groups:
        mat=masks[i]
        if any(old&mat==old for old in held):continue
        minimal.append(i);held.append(mat)
    return {"raw":list(range(len(units))),"producer":producers,"atom_group":atoms,"mask_group":groups,"mask_pareto":minimal}

def requests(q,n):
    hashed=[]
    for prob in (1,3,5,8):
        for i in range(16):
            x=sum(1<<j for j in range(n) if int(h(f"r31/{prob}/{i}/{q}/{j}")[:16],16)*10 < prob*(1<<64))
            hashed.append(x)
    return hashed,[1<<j for j in range(n)]

def build():
    plan,base,data=available()
    if (D/"result-seal.json").exists():return
    dbpath=base/"physical";dbpath.mkdir(exist_ok=True)
    registry=sqlite3.connect(dbpath/"basis.sqlite");registry.execute("CREATE TABLE a(q INTEGER,a INTEGER,path BLOB,line INTEGER,sha BLOB,n INTEGER,PRIMARY KEY(q,a)) WITHOUT ROWID")
    registry.execute("CREATE TABLE appearance(q INTEGER,e INTEGER,a INTEGER,PRIMARY KEY(q,e,a)) WITHOUT ROWID")
    full=sqlite3.connect(dbpath/"fallback.sqlite");full.execute("CREATE TABLE r(q INTEGER,m INTEGER,rank INTEGER,cid INTEGER,mask INTEGER,PRIMARY KEY(q,m,rank)) WITHOUT ROWID")
    db={}
    for mode in plan["modes"]:
        for k in plan["K"]:
            con=sqlite3.connect(dbpath/(mode+str(k)+".sqlite"))
            con.execute("CREATE TABLE r(q INTEGER,m INTEGER,rank INTEGER,cid INTEGER,mask INTEGER,PRIMARY KEY(q,m,rank)) WITHOUT ROWID")
            con.execute("CREATE TABLE cert(q INTEGER,m INTEGER,omitted INTEGER,complete INTEGER,PRIMARY KEY(q,m)) WITHOUT ROWID")
            db[mode,k]=con
    byq={};costs={};trials={};verification=0;proof=0;timingcases=[]
    for ix,q in enumerate(plan["qids"]):
        v=data[q];E=v["events"];atoms=v["atoms"];hashed,singles=requests(q,len(E));allm=range(1<<len(E))
        registry.executemany("INSERT INTO a VALUES (?,?,?,?,?,?)",((ix,a,bytes.fromhex(path),line,bytes.fromhex(digest),n) for a,(path,line,digest,n) in enumerate(atoms)))
        registry.executemany("INSERT INTO appearance VALUES (?,?,?)",((ix,j,a) for j,(_,ids) in enumerate(E) for a in set(ids)))
        byq[q]={};costs[q]={};trials[q]={}
        # Direct oracle invalidates literal canonical atom ids and never reads the derived dependency masks.
        drop_sets=[frozenset(a for j,(_,atom_ids) in enumerate(E) if mask&(1<<j) for a in atom_ids) for mask in allm]
        for m,(level,order) in enumerate((("line","bm25"),("line","recency"),("block","bm25"),("block","recency"))):
            view=level+"_"+order;t=now();units,priority=ranker(v,level,order);rank_ns=now()-t
            t=now();masks=make_masks(units,E,atoms);mask_ns=now()-t;t=now();arms=selected(units,masks);select_ns=now()-t
            truth=[]
            for drop in drop_sets:truth.append(next((i for i,(_,a) in enumerate(units) if drop.isdisjoint(a)),None))
            possible={i for i in truth if i is not None};assert possible==set(arms["mask_pareto"])
            proof+=len(truth)
            full.executemany("INSERT INTO r VALUES (?,?,?,?,?)",((ix,m,i,cid,masks[i]) for i,cid in enumerate(priority)))
            counts={};size={};trial={}
            for mode,chosen in arms.items():
                for k in plan["K"]:
                    name=mode+str(k);ids=chosen[:k];held=set(ids);omitted=next((z for z in arms["mask_pareto"] if z not in held),len(units))
                    complete=omitted==len(units);con=db[mode,k];size[name]=len(ids)
                    con.executemany("INSERT INTO r VALUES (?,?,?,?,?)",((ix,m,i,priority[i],masks[i]) for i in ids))
                    con.execute("INSERT INTO cert VALUES (?,?,?,?)",(ix,m,omitted,int(complete)))
                    evaluations=[]
                    for mask,target in zip(allm,truth):
                        returned=next((i for i in ids if not masks[i]&mask),None)
                        certain=complete or (returned is not None and returned<omitted)
                        if certain:assert returned==target
                        else:
                            fallback=next((i for i,ms in enumerate(masks) if not ms&mask),None);assert fallback==target
                        evaluations.append((int(certain),int(target is not None and returned==target),int(certain and target is None),
                            int(returned is not None and returned!=target),(0 if certain else target+1 if target is not None else len(units))))
                    verification+=len(evaluations)
                    counts[name]={case:[sum(evaluations[j][z] for j in use) for z in range(5)] for case,use in (("sampled",hashed),("single",singles),("exhaustive",allm))}
                    if m==0 and k==4 and v["group"]=="overlap3":trial[name]=[evaluations[j][0] for j in hashed]
            byq[q][view]={"cases":{"sampled":len(hashed),"single":len(singles),"exhaustive":len(truth)},"sizes":size,"counts":counts,
                          "candidates":len(units),"unique_atoms":len(arms["atom_group"]),"signatures":len(arms["mask_group"]),"minimal":len(arms["mask_pareto"]),
                          "multiple_dependencies":sum(ms.bit_count()>1 for ms in masks)}
            costs[q][view]={"priority_ns":rank_ns,"mask_ns":mask_ns,"selection_ns":select_ns}
            if trial:trials[q]=trial
            if m==0 and v["group"]=="overlap3":
                for mask in hashed:
                    target=truth[mask];timingcases.append((ix,q,mask,None if target is None else priority[target]))
        if (ix+1)%40==0:print("sessions",ix+1,flush=True)
    registry.commit();registry.close();full.commit();full.close()
    for con in db.values():con.commit();con.close()
    save(D/"per-session.json.gz",byq);save(D/"construction-cost.json.gz",costs);save(D/"primary-events.json.gz",trials);save(base/"timing-fixtures.json.gz",timingcases)
    files={f.stem:{"bytes":f.stat().st_size,"sha":sha(f)} for f in sorted(dbpath.glob("*.sqlite"))}
    save(D/"result-seal.json",{"script":sha(Path(__file__)),"source":sha(D/"source-seal.json"),"rows":sha(D/"per-session.json.gz"),"cost":sha(D/"construction-cost.json.gz"),
        "primary":sha(D/"primary-events.json.gz"),"fixtures":sha(base/"timing-fixtures.json.gz"),"physical":files,
        "exhaustive_case_validations":verification,"exhaustive_rank_sets":proof,"fields":["certified","oracle_nonnull","certified_null","wrong_immediate","fallback_candidates_inspected"]})

def physical():
    plan,base,data=available();src=read(D/"result-seal.json");work=read(base/"timing-fixtures.json.gz");folder=base/"physical";methods=plan["modes"]
    conn={}
    for method in methods:
        db=sqlite3.connect(folder/(method+"4.sqlite"))
        db.execute("ATTACH DATABASE ? AS fallback",(str(folder/"fallback.sqlite"),));db.execute("PRAGMA query_only=1");db.execute("BEGIN");conn[method]=db
    first="""SELECT c.complete,c.omitted,x.rank,x.cid FROM cert c LEFT JOIN r x ON x.q=c.q AND x.m=c.m AND x.rank=(
     SELECT rank FROM r WHERE q=c.q AND m=c.m AND (mask & ?)=0 ORDER BY rank LIMIT 1) WHERE c.q=? AND c.m=0"""
    second="SELECT cid FROM fallback.r WHERE q=? AND m=0 AND (mask & ?)=0 ORDER BY rank LIMIT 1"
    rng=random.Random(31074);samples=[];rounds=4
    for rep in range(rounds+1):
        tasks=work.copy();rng.shuffle(tasks)
        for ix,q,mask,expected in tasks:
            order=methods.copy();rng.shuffle(order)
            for method in order:
                db=conn[method];t=now();complete,omit,rank,cid=db.execute(first,(mask,ix)).fetchone()
                count=1
                if not (complete or (rank is not None and rank<omit)):
                    row=db.execute(second,(ix,mask)).fetchone();cid=None if row is None else row[0];count+=1
                elapsed=now()-t;assert cid==expected
                if rep:samples.append([rep,q,mask,method,elapsed,count])
    for db in conn.values():db.execute("COMMIT");db.close()
    save(D/"primary-sql.json.gz",samples);save(D/"physical-seal.json",{"input":sha(D/"result-seal.json"),"rows":sha(D/"primary-sql.json.gz"),
                "sample_size":len(samples),"crossed_requests":len(work),"repeats":rounds})
if __name__=="__main__":build();physical()
