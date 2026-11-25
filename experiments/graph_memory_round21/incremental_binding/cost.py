"""Matched in-memory costs of exact as-of reads under three read frequencies."""
from collections import Counter
from itertools import product
import gc
import math
import random
import statistics
import time
from evaluate import D,env,save,parse_isetrace_record,adapt_isetrace_record,edge_hash,np
from graph_memory.graphs.provenance.builder import _typed_tokens,_iter_string_leaves


def argument(e):
    return (e.raw_arguments,*_iter_string_leaves(e.arguments))


def found(value,pieces):
    return any(value in p for p in pieces)


class Batch:
    def __init__(self):
        self.calls=[];self.values={}
    def event(self,e):
        if e.event_type=="tool_call":
            self.calls.append((e.call_id,argument(e),(e.position.message_index,e.position.sub_index)))
        elif e.event_type=="tool_output":
            pos=(e.position.message_index,e.position.sub_index)
            for _,v in _typed_tokens(e.content):
                self.values[v]=(e.call_id,pos) if v not in self.values else None
    def edges(self):
        return {(v[0],c) for key,v in self.values.items() if v for c,arg,pos in self.calls if pos>v[1] and found(key,arg)}


class Materialized:
    def __init__(self):
        self.values={};self.counts=Counter()
    def event(self,e):
        pos=(e.position.message_index,e.position.sub_index)
        if e.event_type=="tool_call":
            parts=argument(e)
            for key,r in self.values.items():
                if r and pos>r[1] and found(key,parts):
                    r[2].append(e.call_id);self.counts[(r[0],e.call_id)]+=1
        elif e.event_type=="tool_output":
            for _,key in _typed_tokens(e.content):
                if key not in self.values:
                    self.values[key]=(e.call_id,pos,[]);continue
                old=self.values[key]
                if old:
                    for c in old[2]:
                        pair=(old[0],c);self.counts[pair]-=1
                        if self.counts[pair]==0:del self.counts[pair]
                    self.values[key]=None
    def edges(self):
        return set(self.counts)


def measure(cls,events,schedule):
    cpu=time.process_time_ns();wall=time.perf_counter_ns()
    obj=cls();out=[]
    for j,e in enumerate(events):
        obj.event(e)
        if j in schedule:out.append(obj.edges())
    elapsed=time.perf_counter_ns()-wall
    used=time.process_time_ns()-cpu
    return used/1e6,elapsed/1e6,out


def summarize(times):
    all_t=sorted({r["t"] for r in times});out={}
    for load in ("last","quarter","each"):
        rset=[r for r in times if r["load"]==load]
        metrics={}
        for name in ("cpu","wall"):
            # Windows process_time_ns can have ~15.6ms granularity; process CPU uses GetProcessTimes.
            # A higher-resolution thread CPU clock is selected by the runner if present.
            b=np.array([statistics.median(r[name] for r in rset if r["t"]==t and r["arm"]=="batch") for t in all_t])
            m=np.array([statistics.median(r[name] for r in rset if r["t"]==t and r["arm"]=="materialized") for t in all_t])
            rng=np.random.default_rng(21015);ix=rng.integers(len(b),size=(10000,len(b)))
            denom=b[ix].sum(axis=1);okay=denom>0
            ci=np.quantile(m[ix].sum(axis=1)[okay]/denom[okay],[.025,.975])
            metrics[name]={"batch_sum_ms":float(b.sum()),"maintained_sum_ms":float(m.sum()),"ratio_of_sums":float(m.sum()/b.sum()),
                           "ratio_ci":ci.tolist(),"batch_median_ms":float(np.median(b)),"maintained_median_ms":float(np.median(m)),
                           "zero_medians":[int((b==0).sum()),int((m==0).sum())]}
        out[load]=metrics
    return out


def main():
    names=env.load(D/"plan.json")["trajectories"][:48]
    refs={r["t"]:r for r in env.load(D/"prefix-outcomes.json.gz")}
    signed={"cohort":names,"protocol":env.pilot.sha(D/"COST_PROTOCOL_RU.md"),"code":env.pilot.sha(D/"cost.py"),
            "native_prefixes":env.pilot.sha(D/"prefix-outcomes.json.gz")}
    save(D/"cost-plan.json",signed)
    times=[];man={}
    for shard in range(8):
        for raw,obj in env.pilot.stream(env.RAW/f"trajectories-{shard:05d}.jsonl"):
            t=obj["session_id"]
            if t not in names:continue
            assert env.hashlib.sha256(raw).hexdigest()==refs[t]["source_sha256"]
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            steps=[];pending=0
            for j,e in enumerate(tr.events):
                if e.event_type=="tool_call":pending+=1
                elif e.event_type=="tool_output":
                    pending-=1
                    if not pending:steps.append(j)
            quarter={r["index"] for r in refs[t]["records"]}
            schedules={"last":{steps[-1]},"quarter":quarter,"each":set(steps)}
            gold={r["index"]:r["sha"] for r in refs[t]["records"]}
            conditions=list(product(range(3),schedules));random.Random(t).shuffle(conditions)
            ordinal=names.index(t)
            for rep,load in conditions:
                schedule=schedules[load]
                order=(Batch,Materialized) if (ordinal+rep+list(schedules).index(load))%2 else (Materialized,Batch)
                matched=None
                for method in order:
                    cpu,wall,reads=measure(method,tr.events,schedule)
                    if matched is None:matched=reads
                    else:assert reads==matched
                    for cut,edges in zip(sorted(schedule),reads,strict=True):
                        if cut in gold:assert edge_hash(edges)==gold[cut]
                    times.append({"t":t,"load":load,"rep":rep,"arm":"batch" if method is Batch else "materialized","cpu":cpu,"wall":wall,"reads":len(reads)})
            man[t]=len(steps)
        print("cost shard",shard,len(man),flush=True)
    assert len(times)==48*3*3*2 and set(man)==set(names)
    save(D/"cost-times.json.gz",times);save(D/"cost-results.json",{"timing":summarize(times),"histories":48,
          "max_queries_per_trajectory":max(man.values()),"min_queries_per_trajectory":min(man.values()),
          "each_queries":sum(man.values()),"clock":vars(time.get_clock_info('process_time')),
          "plan":env.pilot.sha(D/"cost-plan.json"),"records":env.pilot.sha(D/"cost-times.json.gz")})

if __name__=="__main__":main()
