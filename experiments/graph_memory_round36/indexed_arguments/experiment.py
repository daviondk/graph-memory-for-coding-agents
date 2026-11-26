"""Evaluate three frozen exact constructions; raw inputs never leave memory."""
from pathlib import Path
from collections import Counter
from itertools import permutations
from time import process_time_ns,perf_counter_ns
import hashlib,itertools,concurrent.futures,platform,sys
from indexed import PreparedFeeds,all_leaves,uncovered_leaves,eager,contains
from graph_memory.graphs.provenance.builder import _iter_string_leaves
from common_match import rows,sha,load,put,l, np
from timing import cycles

D=Path(__file__).resolve().parent
prev=D.parent/"deferred_match"
methods=("A","B","C")

def model(method):
    return eager.HistoricalFeeds() if method=="A" else PreparedFeeds({"B":all_leaves,"C":uncovered_leaves}[method])

def seal():
    assert sha(prev/"manifest.json")=="8c99e9c0c0e06eed648176381e7ab80f3ae628b67e2f5ea1457bb00d50a6b423"
    put(D/"plan.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),operator=sha(D/"indexed.py"),
        code=sha(Path(__file__)),panel=load(prev/"plan.json")["timed_ids"],previous=sha(prev/"manifest.json"),
        primary="C/A thread cycles",seed=360614,replicates=6))

def inspect_call(cnt,e,origin):
    raw=e.raw_arguments
    leaves=all_leaves(e)
    unique=tuple(dict.fromkeys(leaves))
    rem=uncovered_leaves(e)
    pos=(e.position.message_index,e.position.sub_index)
    cnt["calls"]+=1
    cnt["B_C_list_builds"]+=1
    cnt["B_C_yielded_prep"]+=len(leaves)
    cnt["B_stored"]+=len(leaves)
    cnt["C_distinct_raw_containment_checks"]+=len(unique)
    cnt["C_stored"]+=len(rem)
    cnt["C_nonempty_calls"]+=bool(rem)
    for val,src in origin.items():
        if src is None or src[1]>=pos:continue
        cnt["all_predicates"]+=1
        if val in raw:
            cnt["raw_hits"]+=1
            continue
        cnt["A_recursive_starts"]+=1
        # A skips prep, its iterator yields exactly the visited leaves in native order.
        matched=False
        for leaf in leaves:
            cnt["A_B_leaf_substr_checks"]+=1
            if val in leaf:
                matched=True
                break
        reduced=False
        for leaf in rem:
            cnt["C_leaf_substr_checks"]+=1
            if val in leaf:
                reduced=True
                break
        assert matched==reduced
        cnt["decoded_only_hits"]+=matched

def audit(sh):
    data={}
    previous=load(prev/f"counters-{sh}.json.gz")
    for t,events,chunks,geom in rows(sh):
        count=Counter(); models=[model(m) for m in methods]
        cuts=l.parent.cuts_for(events)
        checks=[]
        for i,e in enumerate(events):
            if e.event_type not in ("tool_call","tool_output"):continue
            has=e.event_type=="tool_output" and chunks[e.call_id]>0
            if e.event_type=="tool_call":inspect_call(count,e,models[0].producer)
            for m in models:m.consume(e,has)
            ref=models[0]
            for other in models[1:]:
                assert ref.open_calls==other.open_calls and ref.producer==other.producer
                assert ref.visible_outputs==other.visible_outputs and ref.observed_pairs==other.observed_pairs
            count["events"]+=1
            count["identity_integral"]+=len(ref.observed_pairs)
            for cut,idx in zip(("25","50","75","100"),cuts):
                if idx==i:
                    pairs=len(ref.observed_pairs);npu=sum(chunks[a]*chunks[b] for a,b in ref.observed_pairs)
                    assert (pairs,npu)==tuple(previous[t]["cuts"][cut])
                    checks.append(cut)
        old=previous[t]["counts"]
        assert len(checks)==4
        assert count["events"]==old["event_checks"] and count["identity_integral"]==old["observed_identity_integral"]
        assert count["all_predicates"]==old.get("predicate_old",0)
        data[t]={"counts":dict(count),"cuts":len(checks)}
    p=D/f"audit-{sh}.json.gz";put(p,data)
    print("audit",sh,len(data),flush=True)
    return p.name,sha(p)

def run_timing():
    panel=load(D/"plan.json")["panel"]
    per={}
    orders=list(permutations(methods))
    for sh in range(8):
        for t,events,chunks,_ in rows(sh,panel):
            steps=[(e,e.event_type=="tool_output" and chunks[e.call_id]>0) for e in events if e.event_type in ("tool_call","tool_output")]
            def run(k):
                m=model(k)
                for e,has in steps:m.consume(e,has)
                return m.observed_pairs
            truth=run("A"); assert run("B")==truth and run("C")==truth
            block=[]
            shift=int.from_bytes(hashlib.sha256(t.encode()).digest()[:8],"big")%6
            for j in range(6):
                order=orders[(shift+j)%6];trial={}
                for k in order:
                    w=perf_counter_ns();p=process_time_ns();c=cycles()
                    observed=run(k)
                    dt=cycles()-c;dp=process_time_ns()-p;dw=perf_counter_ns()-w
                    assert observed==truth
                    trial[k]=[int(dt),dp,dw]
                block.append(trial)
            per[t]={"samples":block,"schedule_shift":shift}
        print("timing",sh,len(per),flush=True)
    assert set(panel)==set(per)
    f=D/"clock_samples.json.gz";put(f,per)
    put(D/"timing-seal.json",dict(data=sha(f),plan=sha(D/"plan.json"),python=platform.python_version(),
        sequence=["thread_cycles","process_time_ns","perf_counter_ns"]))

def run_audit():
    with concurrent.futures.ProcessPoolExecutor(2) as pool:out=dict(pool.map(audit,range(8)))
    put(D/"count-seal.json",dict(files=out,plan=sha(D/"plan.json")))

if __name__=="__main__":
    op=sys.argv[1]
    if op=="seal":seal()
    elif op=="timing":run_timing()
    elif op=="audit":run_audit()
    else:raise ValueError(op)
