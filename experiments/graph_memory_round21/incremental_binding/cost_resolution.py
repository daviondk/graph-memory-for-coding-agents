"""Repeat identical trajectories in paired blocks to overcome Windows CPU ticks."""
import collections
import math
import random
import statistics
import time
from cost import Batch,Materialized,D,env,save,summarize,edge_hash,parse_isetrace_record,adapt_isetrace_record


def measure(cls,events,cuts,repeats):
    cpu=time.process_time_ns();wall=time.perf_counter_ns()
    for _ in range(repeats):
        obj=cls();read=[]
        for j,e in enumerate(events):
            obj.event(e)
            if j in cuts:read.append(obj.edges())
    elapsed=(time.perf_counter_ns()-wall)/1e6;used=(time.process_time_ns()-cpu)/1e6
    return used/repeats,elapsed/repeats,read


def main():
    plan=env.load(D/"cost-plan.json");times=env.load(D/"cost-times.json.gz")
    refs={r["t"]:r for r in env.load(D/"prefix-outcomes.json.gz")}
    old=collections.defaultdict(list)
    for r in times:old[r["t"],r["load"],r["arm"]].append(r["wall"])
    reps={}
    for t in plan["cohort"]:
        reps[t]={key:min(512,max(1,math.ceil(128/min(statistics.median(old[t,key,arm]) for arm in ("batch","materialized"))))) for key in ("last","quarter","each")}
    save(D/"cost-resolution-plan.json",{"blocks":reps,"protocol":env.pilot.sha(D/"COST_RESOLUTION_RU.md"),"code":env.pilot.sha(D/"cost_resolution.py"),
        "parent":env.pilot.sha(D/"cost-plan.json"),"timings":env.pilot.sha(D/"cost-times.json.gz")})
    records=[]
    for shard in range(8):
        shard_start=len(records)
        for raw,obj in env.pilot.stream(env.RAW/f"trajectories-{shard:05d}.jsonl"):
            t=obj["session_id"]
            if t not in reps:continue
            assert env.hashlib.sha256(raw).hexdigest()==refs[t]["source_sha256"]
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            steps=[];pending=0
            for j,e in enumerate(tr.events):
                if e.event_type=="tool_call":pending+=1
                elif e.event_type=="tool_output":
                    pending-=1
                    if not pending:steps.append(j)
            gold={r["index"]:r["sha"] for r in refs[t]["records"]}
            schedules={"last":{steps[-1]},"quarter":set(gold),"each":set(steps)}
            blocks=[(r,k) for r in range(3) for k in schedules]
            random.Random("blocks"+t).shuffle(blocks)
            ord=plan["cohort"].index(t)
            for r,k in blocks:
                pair=None
                for method in ((Batch,Materialized) if (ord+r+list(schedules).index(k))%2 else (Materialized,Batch)):
                    n=reps[t][k];cpu,wall,reads=measure(method,tr.events,schedules[k],n)
                    if pair is None:pair=reads
                    else:assert pair==reads
                    for cut,p in zip(sorted(schedules[k]),reads,strict=True):
                        if cut in gold:assert edge_hash(p)==gold[cut]
                    records.append(dict(t=t,load=k,rep=r,arm="batch" if method is Batch else "materialized",
                                        cpu=cpu,wall=wall,inner_repeats=n,reads=len(reads)))
        save(D/f"cost-resolution-shard-{shard}.json.gz",records[shard_start:])
        print("timing shard",shard,len(records),flush=True)
    assert len(records)==864
    save(D/"cost-resolution-times.json.gz",records)
    save(D/"cost-resolution-results.json",{"timings":summarize(records),"zero_blocks":sum(r["cpu"]==0 for r in records),
         "blocks":len(records),"shortest_cpu_block_ms":min(r["cpu"]*r["inner_repeats"] for r in records),
         "inner_passes":sum(r["inner_repeats"] for r in records),"source":env.pilot.sha(D/"cost-resolution-plan.json"),
         "results":env.pilot.sha(D/"cost-resolution-times.json.gz")})

if __name__=="__main__":main()
