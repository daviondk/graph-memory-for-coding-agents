"""Predict from each past cache before inserting the returned editor bytes."""
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
import numpy as np
from cache import ARMS,Cache

HERE=Path(__file__).resolve().parent
PAST=HERE.parents[1]/"graph_memory_round57/agent_trace"
CAPS=(4096,16384,65536)
CASES=[(b,12,a,False) for b in CAPS for a in ARMS]+[
    (16384,h,a,False) for h in (8,16) for a in ("file","file_intern")]+[
    (16384,0,a,True) for a in ("global","file")]
PRIMARY=("16384_12_file_intern","16384_12_file")

def label(cap,row,arm,legacy):return f"{cap}_{row}_{arm}"

def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)

def digest(p):return sha256(p.read_bytes()).hexdigest()

def save(p,obj,verify):
    if verify:assert load(p)==obj,p;return
    b=(json.dumps(obj,separators=(",",":"),sort_keys=True)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)

def freeze(verify):
    traces=load(PAST/"prefixes.json.gz")
    logs=[];forecasts=[]
    for trace in traces:
        caches={label(*s):Cache(s[2],s[0],s[1],s[3]) for s in CASES}
        for t,event in enumerate(trace["events"]):
            if event[0]=="barrier":
                for c in caches.values():c.clear()
            if len(event)!=3:continue
            action,path,lines=event
            tag={k:trace[k] for k in ("actor","repo","issue")}
            tag.update(at=t,action=action,path=path,bytes=sum(s for _,_,s in lines))
            # Issue the address lookup with only the path and the requested line numbers.
            line_ids=[num for num,_,_ in lines]
            prior={}
            for key in PRIMARY:
                cells=caches[key].cells
                prior[key]=[cells[(path,n)].uid if (path,n) in cells else -1 for n in line_ids]
            forecasts.append(dict(issue=trace["issue"],actor=trace["actor"],at=t,line_n=line_ids,forecasts=prior))
            scores={};state={}
            for key,c in caches.items():
                scores[key]=c.serve(path,lines)
            for key,c in caches.items():
                state[key]=c.update(path,lines)
                assert state[key][0]<=c.cap
                if key in prior:
                    assert scores[key][0]==sum(size for pred,(_,uid,size) in zip(prior[key],lines) if pred==uid)
            logs.append(dict(**tag,score=scores,state=state))
    save(HERE/"prior-addresses.json.gz",forecasts,verify)
    save(HERE/"windows.json.gz",logs,verify)
    sources={"projection":digest(PAST/"prefixes.json.gz")}
    for n in ("PROTOCOL_RU.md","cache.py","replay.py","windows.json.gz","prior-addresses.json.gz"):
        sources[n]=digest(HERE/n)
    save(HERE/"seal.json",sources,verify)
    print("Forecast receipts for",len(logs),"windows",flush=True)

def score(rows):
    if not rows:return {}
    den=sum(r["bytes"] for r in rows);out={}
    for key in rows[0]["score"]:
        values=[r["score"][key] for r in rows];stats=[r["state"][key] for r in rows]
        total=sum(v[0] for v in values)
        out[key]=dict(hit_bytes=total,hit_rate=total/den if den else 0,full=sum(v[1] for v in values),
            conflict=sum(v[2] for v in values),peak=max(s[0] for s in stats),
            pointer_instances=sum(s[2] for s in stats),bypassed_or_evicted=sum(s[3] for s in stats))
    return dict(windows=len(rows),total_bytes=den,arms=out)

def contrast(rows,a,b):
    groups={}
    for r in rows:
        record=groups.setdefault(r["issue"],[0,0])
        record[0]+=r["score"][a][0]-r["score"][b][0];record[1]+=r["bytes"]
    arr=np.array(list(groups.values()),dtype=np.int64);n=len(arr)
    rng=np.random.default_rng(58017)
    weights=rng.multinomial(n,[1/n]*n,size=20000)
    num,den=(weights@arr).T
    rates=num[den>0]/den[den>0]
    diffs=[r["score"][a][0]-r["score"][b][0] for r in rows]
    return dict(delta_pp=float(100*arr[:,0].sum()/arr[:,1].sum()),
        ci_pp=(100*np.quantile(rates,[.025,.975])).tolist(),issues=n,
        win_windows=sum(d>0 for d in diffs),loss_windows=sum(d<0 for d in diffs),tie_windows=diffs.count(0),
        win_issues=int((arr[:,0]>0).sum()),loss_issues=int((arr[:,0]<0).sum()))

def grade(verify):
    rows=load(HERE/"windows.json.gz");seal=load(HERE/"seal.json")
    assert digest(PAST/"prefixes.json.gz")==seal["projection"]
    assert all(digest(HERE/n)==v for n,v in seal.items() if n!="projection")
    reference=load(PAST/"forecasts.json.gz")
    old={(t["issue"],t["actor"],r["at"]):r for t in reference for r in t["cache"]}
    assert len(old)==len(rows)
    for r in rows:
        o=old[r["issue"],r["actor"],r["at"]]
        assert r["score"]["16384_0_file"]==o["served"]["graph"] and r["score"]["16384_0_global"]==o["served"]["lru"]
    repos=sorted({r["repo"] for r in rows},key=lambda name:sha256(("58017/"+name).encode()).digest())
    actors=sorted({r["actor"] for r in rows})
    def subgroup(rs):
        z=score(rs)
        return dict(windows=z["windows"],bytes=z["total_bytes"],
                    **{m:z["arms"][m] for m in PRIMARY},contrast=contrast(rs,*PRIMARY))
    out=dict(all=score(rows),primary=contrast(rows,*PRIMARY),
        repos={rp:subgroup([r for r in rows if r["repo"]==rp]) for rp in repos},
        actors={act:subgroup([r for r in rows if r["actor"]==act]) for act in actors},
        folds=[dict(repos=part,**subgroup([r for r in rows if r["repo"] in part]))
               for part in (repos[:len(repos)//2],repos[len(repos)//2:])])
    save(HERE/"results.json",out,verify)
    print("Matched",len(rows),"old windows; primary",out["primary"])
    print({k:(r["hit_bytes"],r["full"]) for k,r in out["all"]["arms"].items() if k.startswith("16384_12")})
if __name__=="__main__":
    verify="--verify" in sys.argv
    if sys.argv[1]=="freeze":freeze(verify)
    elif sys.argv[1]=="grade":grade(verify)
    else:raise SystemExit("use freeze or grade")
