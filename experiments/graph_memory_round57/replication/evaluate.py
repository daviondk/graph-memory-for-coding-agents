"""Registered paired R57 replay. No fitting or threshold selection."""
import argparse
from collections import Counter,deque
from hashlib import sha256
from heapq import nlargest
from itertools import product
import random
from statistics import fmean
import sys

from collect import HERE,NAMES,R56,canonical,load,save
sys.path.insert(0,str(R56/"size_control"))
from evaluate_size import BASE,METHODS,Retained,UNIT,select

PRIMARY=("fill6_norm","own_norm")
CONTROL=("fill6_norm_bytes","own_norm_bytes")
ALL=METHODS+CONTROL

def size_limited(js,events,cap):
    selected=[]
    for j in js:
        size=4*len(events[j])
        if size<=cap:
            selected.append(j);cap-=size
    return selected

def replay(name,stream):
    ids={};freq=Counter();window=deque()
    state=Retained(8,"last",name);rows=[]
    for t,(sha,raw) in enumerate(stream):
        paths=raw if len(raw)<=64 else []
        if t>=len(stream)//2 and len(paths)>=2:
            anchor_path=paths[int(sha,16)%len(paths)]
            a=ids.get(anchor_path,-1)
            gold={ids[p] for p in paths if p!=anchor_path and p in ids}
            groups,n=select(state,a)
            cap=min(4*sum(len(state.events[j]) for j in groups[m]) for m in PRIMARY)
            for m in PRIMARY:groups[m+"_bytes"]=size_limited(groups[m],state.events,cap)
            assert len(groups[PRIMARY[0]])==len(groups[PRIMARY[1]])
            methods={}
            for m in ALL:
                js=groups[m]
                assert len(js)<=8 and all(j<t for j in js)
                votes=Counter();members=0
                for j in js:
                    ep=state.events[j]
                    weight=UNIT//(len(ep)-1) if "_norm" in m else 1
                    for f in ep:votes[f]+=weight
                    members+=len(ep)
                if m.endswith("_bytes"):assert 4*members<=cap
                rank=nlargest(8,(f for f in range(len(ids)) if f!=a),key=lambda f:(votes[f],freq[f],-f))
                methods[m]=dict(hit_count=len(gold.intersection(rank)),rank=rank,events=js,bytes=4*members)
            rows.append(dict(t=t,sha=sha,anchor=a,target_n=len(paths)-1,known_targets=sorted(gold),
                             available=n,wire_budget=cap,methods=methods))
        codes=[ids.setdefault(p,len(ids)) for p in paths]
        if len(window)==32:freq.subtract(window.popleft())
        window.append(codes);freq.update(codes)
        state.ingest(codes,paths,sha,t)
    return rows

def summarize(rows):
    out={}
    for m in ALL:
        items=[r["methods"][m] for r in rows]
        out[m]=dict(n=len(rows),recall=fmean(p["hit_count"]/r["target_n"] for p,r in zip(items,rows)),
                    hit=sum(p["hit_count"]>0 for p in items),event_reads=sum(len(p["events"]) for p in items),
                    bytes=sum(p["bytes"] for p in items))
    return out

def difference(rows,pair):
    a,b=pair;vals=[(r["methods"][a]["hit_count"]-r["methods"][b]["hit_count"])/r["target_n"] for r in rows]
    return dict(delta=fmean(vals),win=sum(n>0 for n in vals),loss=sum(n<0 for n in vals),
                tie=sum(n==0 for n in vals),n=len(rows))

def quantile(data,p):
    ix=(len(data)-1)*p
    lo=int(ix);f=ix-lo
    return data[lo]*(1-f)+data[min(lo+1,len(data)-1)]*f

def paired(groups,pair):
    per={repo:difference(rows,pair) for repo,rows in groups.items() if rows}
    vals=[r["delta"] for r in per.values()]
    rng=random.Random(57061)
    boot=sorted(fmean(rng.choices(vals,k=len(vals))) for _ in range(20000))
    point=fmean(vals)
    perms=[fmean(s*v for s,v in zip(sign,vals)) for sign in product((-1,1),repeat=len(vals))]
    return dict(per_repo=per,macro_delta=point,ci95=[quantile(boot,.025),quantile(boot,.975)],
                signflip_p=sum(abs(t)>=abs(point)-1e-12 for t in perms)/len(perms),
                pooled=difference([r for rows in groups.values() for r in rows],pair))

def main():
    arg=argparse.ArgumentParser();arg.add_argument("--verify",action="store_true");args=arg.parse_args()
    def record(f,o):
        if args.verify:assert o==load(HERE/f)
        else:save(HERE/f,o)
    data=load(HERE/"events.json.gz");seal=load(HERE/"data-seal.json")
    assert sha256(canonical(data)).hexdigest()==seal["events_digest"] and set(data)==set(NAMES)
    groups={repo:replay(repo,data[repo]) for repo in NAMES}
    all_rows=[r for rs in groups.values() for r in rs]
    repos={repo:summarize(rs) for repo,rs in groups.items() if rs}
    macro={m:fmean(z[m]["recall"] for z in repos.values()) for m in ALL}
    out=dict(projects=repos,zero_queries=[rp for rp,rs in groups.items() if not rs],
             pooled=summarize(all_rows),macro=macro,primary=paired(groups,PRIMARY),wire_control=paired(groups,CONTROL),
             n=len(all_rows),eligible={rp:len(rs) for rp,rs in groups.items()})
    record("queries.json.gz",groups);record("results.json",out)
    print("projects",out["eligible"])
    print("primary",out["primary"]);print("wire",out["wire_control"])
    print([(m,round(100*v,2)) for m,v in macro.items()])
if __name__=="__main__":main()
