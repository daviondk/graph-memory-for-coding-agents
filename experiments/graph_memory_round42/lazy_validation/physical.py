"""Replay both plans against literal source text, with one on-demand index per edit/plan."""
from collections import defaultdict
from time import perf_counter_ns
import sys
import numpy as np
from evaluate import D,SOURCE,read,save,sha,select,materialize
sys.path.insert(0,str(SOURCE))
from shared import inputs,stream

class SourceReader:
    def __init__(self, old,new,view,blocks):
        self.old=old
        self.new=new
        self.view=view
        self.blocks=blocks
        self.lines=None
        self.requests=0
        self.ids=[]
    def find(self,i):
        if self.lines is None:
            self.lines=(self.old.split("\n"),self.new.split("\n"))
            self.locations=defaultdict(list)
            for n,s in enumerate(self.lines[1]):
                self.locations[s].append(n)
            self.requests+=1
        a,b=self.lines
        low,high=self.blocks[i]
        want=a[low-1:high]
        if len(want)!=high-low+1:
            return None
        from hashlib import sha256
        if any(sha256(line.encode()).hexdigest()!=self.view[j] for j,line in enumerate(want,low)):
            return None
        rare=min(range(len(want)),key=lambda j:len(self.locations[want[j]]))
        result=None
        for pos in self.locations[want[rare]]:
            start=pos-rare
            if start<0 or b[start:start+len(want)]!=want:
                continue
            if result is not None:
                return None
            result=[start+1,start+len(want)]
        return result

def main():
    from statistics import median
    events,plans,views=inputs()
    forecast=read(D/"forecasts.json.gz")
    assert sha(D/"forecasts.json.gz")==read(D/"forecast-seal.json")["forecast"]
    timings={};line_checks=0;verified=0
    from hashlib import sha256
    for k,e,_,old,new in stream(events):
        f=forecast[k]
        plan=plans[e["run"]][str(e["at"])][0]
        rows=[(i,p,c,u) for i,p,l,h,c,u,v in plan]
        blocks={i:(l,h) for i,p,l,h,c,u,v in plan if p==e["path"]}
        view={i:h for i,h,*_ in views[e["run"]][str(e["view"])]}
        ready={};delta=e["delta"]
        for i,(lo,hi) in blocks.items():
            if hi<e["start"]: ready[i]=[lo,hi]
            if lo>e["end"]: ready[i]=[lo+delta,hi+delta]
        pending=set(blocks)-set(ready)
        assert sorted(pending)==f["uncertain"]
        samples=defaultdict(list)
        order=["eager","exact"] if int(k[0],16)%2 else ["exact","eager"]
        for rep in range(3 if e["held"] else 1):
            for policy in order if rep%2==0 else reversed(order):
                t=perf_counter_ns()
                reader=SourceReader(old,new,view,blocks);addresses=dict(ready)
                def obtain(i):
                    addr=reader.find(i)
                    if addr is not None:addresses[i]=addr
                    return addr is not None
                if policy=="exact":
                    ids,asked,_=materialize(rows,pending,obtain,select,1024)
                else:
                    for i in sorted(pending):obtain(i)
                    ids=list(select([r for r in rows if r[0] not in blocks or r[0] in addresses])[0])
                    asked=sorted(pending)
                ns=perf_counter_ns()-t
                assert ids==f["ids"]
                assert {str(i):addresses[i] for i in ids if i in blocks}==f["addresses"]
                if policy=="exact":assert asked==f["runs"]["all_completions"]["asked"]
                samples[policy].append(ns)
        after=new.split("\n")
        for i in f["ids"]:
            if i not in blocks:continue
            low,high=blocks[i]
            start,end=f["addresses"][str(i)]
            want=[view[j] for j in range(low,high+1)]
            assert [sha256(s.encode()).hexdigest() for s in after[start-1:end]]==want
            line_checks+=len(want);verified+=1
        timings[k]=dict(samples)
    save(D/"physical-timings.json.gz",timings)
    groups=defaultdict(lambda:np.zeros(2))
    medians=defaultdict(list)
    for k,t in timings.items():
        f=forecast[k]
        if f["held"]:
            for j,p in enumerate(["eager","exact"]):
                m=median(t[p]);medians[p].append(m)
                groups[f["issue"]][j]+=m
    pairs=np.stack([groups[k] for k in sorted(groups)])
    w=np.random.default_rng(420137).integers(len(groups),size=(10000,len(groups)))
    z=pairs[w].sum(axis=1);ratio=z[:,0]/z[:,1]
    out=dict(issues_held=len(groups),events=len(timings),selected_target_lines=line_checks,selected_target_blocks=verified,
        total_ms=(pairs.sum(axis=0)/1e6).tolist(),speedup=pairs[:,0].sum()/pairs[:,1].sum(),ci=np.quantile(ratio,[.025,.975]).tolist(),
        median_us={p:median(t)/1e3 for p,t in medians.items()},timing_sha=sha(D/"physical-timings.json.gz"),mismatches=0)
    save(D/"physical-check.json",out);print(out)
if __name__=="__main__":main()
