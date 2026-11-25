"""Evaluate only after the delivered source coordinates have been sealed."""
from collections import Counter, defaultdict
import sqlite3
import numpy as np
from project import D, WORK, UP, TOK, read, sha, write

STATES = ["missing_field", "no_intersection", "partial", "fragmented", "intact"]
COLUMNS = ["full_support", "intact", "coverage", "tokens", "bytes", "pieces", "state"]

def union(pairs):
    merged=[]
    for l,h in sorted(pairs):
        if merged and merged[-1][1]>=l:
            merged[-1][1]=max(merged[-1][1],h)
        else:
            merged.append([l,h])
    return merged

def measure(gold,parts):
    shown=defaultdict(list)
    for e,l,h in parts:
        assert 0<=l<h
        shown[e].append((l,h))
    original=defaultdict(list)
    status=4
    for e,l,h in gold:
        original[e].append((l,h))
        spans=shown.get(e,[])
        if not spans:
            status=0
        elif not any(x<h and y>l for x,y in spans):
            status=min(status,1)
        elif not any(x<=l and h<=y for x,y in spans):
            continuous=any(x<=l and h<=y for x,y in union(spans))
            status=min(status,3 if continuous else 2)
    total=covered=0
    for e,pairs in original.items():
        slices=union(shown.get(e,[]))
        for l,h in union(pairs):
            total+=h-l
            covered+=sum(max(0,min(h,y)-max(l,x)) for x,y in slices)
    assert total>0 and (covered==total)==(status>=3)
    return [int(status>=3),int(status==4),covered/total],status

def contrasts(rows,traces,pairs):
    # Cluster influence sums for centered multiplier bootstrap; ordinary paired
    # percentile intervals are obtained by sampling whole trajectories with replacement.
    labels,idx=np.unique(traces,return_inverse=True)
    n=len(rows);g=len(labels); cnt=np.bincount(idx)
    a=np.array([[row[k][col]-row[j][col] for k,j,col in pairs] for row in rows])
    sums=np.stack([np.bincount(idx,weights=x,minlength=g) for x in a.T],axis=1)
    avg=a.mean(axis=0); center=sums-cnt[:,None]*avg
    se=np.sqrt((center**2).sum(axis=0)*g/(g-1))/n
    rng=np.random.default_rng(2301)
    shifts=[]; percent=[]
    for _ in range(100):
        mult=rng.choice([-1,1],size=(100,g))
        z=mult@center/n
        nz=np.where(se>0,se,1)
        shifts.extend(np.max(np.abs(z/nz),axis=1))
        ids=rng.integers(g,size=(100,g))
        percent.extend(sums[ids].sum(axis=1)/cnt[ids].sum(axis=1)[:,None])
    cutoff=np.quantile(shifts,.95);low,high=np.quantile(percent,[.025,.975],axis=0)
    return [dict(left=k,right=j,column=COLUMNS[c],wins=int(sum(a[:,i]>0)),losses=int(sum(a[:,i]<0)),
                 delta=avg[i],cluster95=[low[i],high[i]],simul95=[avg[i]-cutoff*se[i],avg[i]+cutoff*se[i]])
            for i,(k,j,c) in enumerate(pairs)]

def main():
    seal=read(D/"receipt-lock.json");inputs=read(D/"inputs.json")
    assert sha(D/"inputs.json")==seal["inputs"] and sha(D/"project.py")==seal["code"]
    assert sha(D/"registry.sqlite")==inputs["registry_sha"] and sha(TOK)==inputs["tokenizer"]
    assert sha(D/"PROTOCOL_RU.md")==inputs["protocol"]
    ref=read(UP/"strict-metrics.json.gz")
    goldpath=WORK/"graph_memory_round18/isetrace_official/gold-spans.json.gz"
    gold=read(goldpath)
    rows={}; totals=defaultdict(list); cnts=defaultdict(Counter); old_causes=defaultdict(Counter)
    db=sqlite3.connect((D/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    book=defaultdict(dict)
    for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address"):
        book[t][(eid,ptr)]=e
    db.close()
    for f,dig in sorted(seal["files"].items()):
        assert sha(D/f)==dig
        for row in read(D/f):
            q,t=row["q"],row["t"]; assert q not in rows
            gg=[(book[t].get((v["event_id"],v["json_pointer"]),-1),v["char_start"],v["char_end"]) for v in gold[q]]
            vals={}
            for arm,rep in row["arms"].items():
                for cap,(tok,byt,parts,ctx_sha) in rep["paid"].items():
                    assert tok<=int(cap) and len(ctx_sha)==64
                    m,status=measure(gg,parts)
                    key=f"{arm}/{cap}"
                    data=m+[tok,byt,len(parts),status]
                    vals[key]=data;totals[key].append(data);cnts[key][STATES[status]]+=1
                    if cap=="2048" and arm.endswith("/bare"):
                        old=ref[arm.split("/")[0]][q]
                        assert t==old["t"] and old["tokens"]==tok and old["full_support"]==m[0] and abs(old["coverage"]-m[2])<1e-12
            a,b=[vals[k+"/bare/2048"] for k in ["ratio","skip"]]
            if a[0]!=b[0]:
                loser=a if a[0]==0 else b
                old_causes["micro_win" if a[0] else "micro_loss"][STATES[loser[-1]]]+=1
            rows[q]={"t":t,"values":vals}
    assert len(rows)==2000 and set(rows)==set(ref["ratio"])==set(ref["skip"]) and len({v["t"] for v in rows.values()})==1207
    assert [sum(old_causes[k].values()) for k in ["micro_win","micro_loss"]]==[114,70]
    pairs=[("ratio/short/2048","skip/short/2048",0),("ratio/merged/2048","ratio/short/2048",1)]
    ordered=[rows[q] for q in sorted(rows)]
    stats=contrasts([r["values"] for r in ordered],[r["t"] for r in ordered],pairs)
    matrix=defaultdict(Counter)
    for row in ordered:
        v=row["values"]
        matrix[STATES[v["skip/bare/2048"][-1]]][STATES[v["ratio/bare/2048"][-1]]]+=1
    summary={}
    for k,v in sorted(totals.items()):
        a=np.asarray(v)
        summary[k]={"hits":int(a[:,0].sum()),"intact":int(a[:,1].sum()),"states":cnts[k],
                    **{COLUMNS[j]:float(a[:,j].mean()) for j in range(2,6)}}
    write(D/"per-query.json.gz",{"columns":COLUMNS,"states":STATES,"questions":rows})
    write(D/"results.json",{"q":len(rows),"t":len(book),"verified_bare_query_policy_rows":2*len(rows),
            "gold_sha256":sha(goldpath),"receipt_lock":sha(D/"receipt-lock.json"),"per_query_sha256":sha(D/"per-query.json.gz"),
            "primary":stats,"summaries":summary,"old_switches":old_causes,"bare_transition":matrix})
    print(stats)
    print(dict(old_causes))
if __name__=="__main__":
    main()
