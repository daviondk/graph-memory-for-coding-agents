"""Additional recency policy that pays exactly the same kind of metadata as typed."""
import gzip,time,os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import writer as w
from writer import HERE,DATA,R2,read,save,h,line,rows
def run(k):
    weights=(read(R2/"edit_memory/model.json")["flat"],read(R2/"span_memory/width_model.json"),read(R2/"span_memory/offset.json")["intercept"])
    w.eviction_order=lambda arm,rr,meta,hist,last,t,obj,weights:list(reversed(w.order(rr,meta)))
    N=0;duration=0
    with gzip.open(HERE/f"rich_cuts_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=4) as out,gzip.open(HERE/f"rich_events_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=4) as log:
        for task in rows(DATA/f"source_{k}.jsonl.gz"):
            iid=task["instance"];fixed={"issue":task["issue"],"instance":iid};blobs={b:w.empty("typed") for b in w.BUDGETS}
            for t,event in enumerate(task["events"],1):
                N+=1;obs=[];packets=[]
                for b,blob in blobs.items():
                    start=time.perf_counter_ns();new,metrics=w.transition(blob,event,fixed,weights,b);duration+=time.perf_counter_ns()-start
                    blobs[b]=new;size_before,sz,removed,calls=metrics;obs.append(["rich_lru",b,h(new),sz,size_before,removed,calls])
                    if t%4==0 and t<len(task["events"]):packets.append(["rich_lru",b,h(new),w.payload(new)])
                line(log,[iid,t,obs])
                if packets:line(out,[iid,t,packets])
    return dict(k=k,events=N,transition_ns=duration)
def main():
    save("rich_method_lock.json",{str(p):h(p.read_bytes()) for p in [HERE/"writer.py",HERE/"rich.py",HERE/"METADATA_CONTROL.md",HERE/"method_lock.json"]})
    with ProcessPoolExecutor(3) as pool:timings=list(pool.map(run,range(8)))
    save("rich_timing.json",timings)
    save("rich_lock.json",{p.name:h(p.read_bytes()) for p in [HERE/"rich_method_lock.json",*sorted(HERE.glob("rich_cuts_*.gz")),*sorted(HERE.glob("rich_events_*.gz"))]})
if __name__=="__main__":main()
