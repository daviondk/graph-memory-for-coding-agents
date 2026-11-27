"""Same retained memberships and ranking ties for all size policies."""
import argparse
from collections import Counter,deque
from heapq import nlargest
from math import lcm
from pathlib import Path
from statistics import fmean
import sys

HERE=Path(__file__).resolve().parent
SHARED=HERE.parent/"shared_evidence"
sys.path.insert(0,str(SHARED))
from retain import Retained
sys.path.insert(0,str(HERE.parent/"event_intersection"))
from evaluate import panels,chosen
from run import load,save

UNIT=lcm(*range(1,64))
BASE=("own","small","cap6","cap8","fill6","fill8")
METHODS=BASE+tuple(m+"_norm" for m in BASE)

def select(mem,a):
    recent=sorted(mem.incident.get(a,()),reverse=True)
    own=recent[:8]
    assert set(own)=={t for _,t in mem.owned.get(a,())}
    small=sorted(recent,key=lambda t:(len(mem.events[t]),-t))[:8]
    groups={"own":own,"small":small}
    for cutoff in (6,8):
        short=[t for t in recent if len(mem.events[t])<=cutoff][:8]
        excess=[t for t in recent if len(mem.events[t])>cutoff]
        groups["cap"+str(cutoff)]=short
        groups["fill"+str(cutoff)]=(short+excess)[:8]
    groups.update({m+"_norm":groups[m] for m in BASE})
    return groups,len(recent)

def replay(panel,repo,stream,reference):
    ids={};freq=Counter();window=deque()
    mem=Retained(8,"last",repo)
    result=[]
    ref={r["t"]:r for r in reference}
    for t,(rev,raw) in enumerate(stream):
        paths=raw if len(raw)<=64 else []
        anchor=chosen(panel,rev,t,len(stream),paths)
        if anchor is not None:
            a=ids.get(anchor,-1)
            future={ids.get(path,-2) for path in paths if path!=anchor}
            groups,n=select(mem,a)
            fallback=nlargest(9,range(len(ids)),key=lambda i:(freq[i],-i))
            methods={}
            for name,js in groups.items():
                votes=Counter();members=0
                for j in js:
                    entry=mem.events[j]
                    weight=UNIT//(len(entry)-1) if name.endswith("_norm") else 1
                    for i in entry:votes[i]+=weight
                    members+=len(entry)
                pool=set(fallback).union(votes)
                pool.discard(a)
                ranking=nlargest(8,pool,key=lambda i:(votes[i],freq[i],-i))
                hits=sum(i in future for i in ranking)
                methods[name]=dict(hits=hits,members=members,rank=ranking,events=js)
                if name in ("own","small"):
                    record=ref[t]
                    assert rev==record["sha"] and len(paths)==record["m"]
                    old_hits,_,_,old_reads,old_members=record["methods"]["last_"+name]
                    assert (hits,len(js),members)==(old_hits,old_reads,old_members)
            result.append(dict(t=t,sha=rev,denom=len(paths)-1,anchor=a,available=n,methods=methods))
        codes=[ids.setdefault(path,len(ids)) for path in paths]
        if len(window)==32:freq.subtract(window.popleft())
        freq.update(codes);window.append(codes)
        mem.ingest(codes,paths,rev,t)
    assert len(result)==len(reference)
    return result

def summary(rows):
    out={}
    for name in METHODS:
        rec=[];read=members=hits=zero=plus=minus=0;diff=[]
        for r in rows:
            m=r["methods"][name];s=r["methods"]["small"]
            rec.append(m["hits"]/r["denom"])
            read+=len(m["events"]);members+=m["members"];hits+=m["hits"]>0
            zero+=not m["events"]
            change=m["hits"]-s["hits"]
            plus+=change>0;minus+=change<0;diff.append(change/r["denom"])
        out[name]=dict(n=len(rows),recall=fmean(rec),hit=hits,events=read,members=members,
                       no_evidence=zero,delta_vs_small=fmean(diff),wins_vs_small=plus,
                       ties_vs_small=len(rows)-plus-minus,losses_vs_small=minus)
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("--verify",action="store_true");args=p.parse_args()
    def output(file,value):
        if args.verify:assert load(HERE/file)==value
        else:save(HERE/file,value)
    raw={};results={}
    for panel,inputs in panels().items():
        ref=load(SHARED/f"{panel}8-queries.json.gz")
        groups={rp:replay(panel,rp,stream,ref[rp]) for rp,stream in inputs.items()}
        raw[panel]=groups
        project={rp:summary(qs) for rp,qs in groups.items() if qs}
        results[panel]=dict(projects=project,all=summary([r for qs in groups.values() for r in qs]))
        print(panel,[(m,round(results[panel]["all"][m]["recall"]*100,2)) for m in METHODS],flush=True)
    output("queries.json.gz",raw);output("results.json",results)

if __name__=="__main__":main()
