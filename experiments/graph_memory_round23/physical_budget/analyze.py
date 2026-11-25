"""Paired medians over trajectories, endpoint timing, per-case and durability comparisons."""
from collections import defaultdict,Counter
from statistics import median,mean
import bench as b
from bench import D,np,g,read,save,sha

def stats(pair,seed=13):
    # One median across repeats per trajectory, then matched resampling of trajectories.
    left=np.array([median(pair[q][0]) for q in sorted(pair)],dtype=float)/1000
    right=np.array([median(pair[q][1]) for q in sorted(pair)],dtype=float)/1000
    assert len(left)==len(right)==192 and np.all(right>0)
    rng=np.random.default_rng(seed);rat=[];dif=[]
    for _ in range(20):
        ix=rng.integers(len(left),size=(500,len(left)))
        rat.extend(np.median(left[ix],axis=1)/np.median(right[ix],axis=1))
        dif.extend(np.median(left[ix]-right[ix],axis=1))
    return {"n":len(left),"candidate_us":float(np.median(left)),"baseline_us":float(np.median(right)),
        "ratio":float(np.median(left)/np.median(right)),"ratio_ci":np.quantile(rat,[.025,.975]).tolist(),
        "paired_delta_us":float(np.median(left-right)),"delta_ci":np.quantile(dif,[.025,.975]).tolist()}

def from_two(data,arm_l,arm_r):
    pair=defaultdict(lambda:([],[]))
    for q,arm,time in data:
        if arm in (arm_l,arm_r):pair[q][arm!=arm_l].append(time)
    return stats(pair)

def main():
    files=["plan.json","fixtures.json","build.json","static-times.json.gz","dynamic-complete.json","first-access.json.gz","adversarial.json","native-check.json","native-times.json.gz","native-build.json","NATIVE_PROTOCOL_RU.md","bench.py","greedy_sql.py","first_access.py"]
    files+=[f"dynamic-rep{i}.json.gz" for i in (1,2,3)]+[f"durable-{m}.json" for m in ("raw","covered","cached-rebuild","cached-repair")]
    raw=[r for i in (1,2,3) for r in read(D/f"dynamic-rep{i}.json.gz")];summary={};obs={}
    for B in g.BUDGETS:
        for case in g.CASES:
            group=[r for r in raw if r[2]==B and r[3]==case]
            assert len(group)==3*192*2
            summary[f"{B}/{case}"]=from_two([(z[1],z[4],z[7]+z[8]) for z in group],"repair","rebuild")
            r1=[z for z in group if z[0]==0];a=[z for z in r1 if z[4]=="repair"];base=[z for z in r1 if z[4]=="rebuild"]
            obs[f"{B}/{case}"]={"changed_ids":sum(z[13] for z in a),"changed_cache":sum(z[12] for z in a),"mutated_rows":sum(z[6] for z in a),
                    "repair_read_rows":sum(z[9] for z in a),"full_read_rows":sum(z[9] for z in base),"repair_path":Counter(z[5] for z in a),"cached_input_bytes":sum(z[10] for z in a),"cached_output_bytes":sum(z[11] for z in a)}
    static={};sr=read(D/"static-times.json.gz")
    for B in g.BUDGETS:
        for mode in ("sqlite-cold","warm"):
            a=[r for r in sr if r[0]==mode and r[3]==B]
            static[f"{B}/{mode}"]={m:{"us":median(median(x[5] for x in a if x[2]==i and x[4]==m) for i in range(192))/1000,"total_returned_rows_per_192":sum(x[6] for x in a if x[4]==m and x[1]==0)} for m in ("materialized","priority","scan_sort")}
    nr=read(D/"native-times.json.gz");native={};nf={}
    for case in ("random1","selected1","random8","random32","all"):
        a=[r for r in nr if r[2]==case]
        for other in ("rebuild","cost_certificate","interval_certificate"):
            native[f"{case}/{other}"]=from_two([(z[1],z[3],z[5]) for z in a],"repair",other)
        nf[case]={m:{"vm":sum(z[7] for z in a if z[0]==1 and z[3]==m),"cache_misses":sum(z[9] for z in a if z[3]==m),
            "sql_rows":sum(z[6] for z in a if z[0]==1 and z[3]==m),"median_total_us":median(median(z[5] for z in a if z[3]==m and z[1]==i) for i in range(192))/1000,
            "median_score_update_us":median(median(z[4] for z in a if z[3]==m and z[1]==i) for i in range(192))/1000} for m in ("rebuild","cost_certificate","interval_certificate","repair")}
    fresh=read(D/"first-access.json.gz");first={m:from_two([(z[2],z[3],z[4]+z[5]) for z in fresh if z[0]==m],"repair","rebuild") for m in ("reopen","warm")}
    rows=[];dur={}
    for m in ("raw","covered","cached-rebuild","cached-repair"):
        x=read(D/f"durable-{m}.json");rs=x["results"];rows.extend([(v[1],m,v[6]) for v in rs])
        dur[m]={"median_us":median(z[6] for z in rs)/1000,"commit_median_us":median(z[5] for z in rs)/1000,"p95_total_us":float(np.quantile([z[6] for z in rs],.95))/1000,"wal_bytes":x["wal_bytes_before_checkpoint"]}
    result={"dynamic":summary,"branches":obs,"static":static,"native":native,"native_counters":nf,"fresh_edits":first,"durable":dur,"durable_ratio":from_two(rows,"cached-repair","cached-rebuild"),
         "cases_runtime":{"static":len(sr),"dynamic":len(raw),"native_timed":len(nr),"first_access":len(fresh),"durable":len(rows)},"files":{k:sha(D/k) for k in files}}
    save(D/"results.json",result)
if __name__=="__main__":main()

