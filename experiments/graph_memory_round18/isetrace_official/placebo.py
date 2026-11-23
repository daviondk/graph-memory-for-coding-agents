"""Frozen post-hoc degree-preserving negative controls. Metadata only; no action execution."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

import numpy as np
from discover import BASE, RAW, ROOT, load, pilot, write
from rank import adapt_isetrace_record, parse_isetrace_record
from score import streamgz
from verify_package import evaluate

SEEDS=range(16)
CONTROLS=("strict", "event_degree")
def freeze():
    write("placebo-plan.json",{name:pilot.sha(ROOT/name) for name in ("PLACEBO_PROTOCOL_RU.md","placebo.py","forecast-lock.json","ranking-plan.json","source-lock.json")})
def check(plan):
    for name,digest in load(plan).items():assert pilot.sha(ROOT/name)==digest,name
def ids_by_traj():
    return {r["trajectory_id"] for r in load("cohort.json")}
def metadata():
    check("placebo-plan.json")
    selected=ids_by_traj()
    release={i["path"]:i["sha256"] for i in load("source-lock.json")}
    original=load("forecast-lock.json")["forecasts"]
    archive={}
    for i in range(8):
        name=f"forecasts-shard-{i}.jsonl.gz"
        assert pilot.sha(ROOT/name)==original[name]
        needed={x["trajectory_id"]:x["source_record_sha256"] for x in streamgz(ROOT/name)}
        source=RAW/f"trajectories-{i:05d}.jsonl"
        assert pilot.sha(source)==release["trajectories/"+source.name]
        for raw,row in pilot.stream(source):
            t=row["session_id"]
            if t not in needed:continue
            assert hashlib.sha256(raw).hexdigest()==needed[t] and t not in archive
            tr=adapt_isetrace_record(parse_isetrace_record(row),source_revision=pilot.RAW[1])
            events=(*tr.tool_calls,*tr.tool_outputs)
            ordered=sorted({e.call_id for e in events if e.call_id})
            call={cid:j for j,cid in enumerate(ordered)}
            tools={e.call_id:e.tool_name for e in tr.tool_calls if e.call_id}
            lookup={s:j for j,s in enumerate(sorted({s for s in tools.values() if s is not None}))}
            meta={}
            for e in events:
                j=call.get(e.call_id,-1)
                meta[e.event_id]=[j,"a" if hasattr(e,"raw_arguments") else "o",lookup.get(tools.get(e.call_id),-1)]
            assert len(meta)==len(events)
            archive[t]=meta
        print("metadata shard",i,"cumulative",len(archive),flush=True)
    assert set(archive)==selected
    write("placebo-event-metadata.json.gz",archive)
def make_groups(ranked,meta):
    counters=defaultdict(lambda:{"a":0,"o":0});evs=defaultdict(lambda:{"a":set(),"o":set()})
    opname={};shape={}
    for node in ranked:
        assert len(node["source_spans"])==1
        span=node["source_spans"][0];ev=span["event_id"]
        cid,role,tool=meta[ev];assert role=={"a":"a","o":"o"}[role]
        assert (span["json_pointer"]=="/raw_arguments")== (role=="a")
        shape[node["node_id"]]=(cid,role,node["token_count"])
        if cid<0:continue
        assert cid not in opname or opname[cid]==tool
        opname[cid]=tool;counters[cid][role]+=1;evs[cid][role].add(ev)
    groups={mode:defaultdict(list) for mode in CONTROLS}
    for cid,ct in counters.items():
        if min(ct.values())==0:continue
        base=(opname[cid],len(evs[cid]["a"]),len(evs[cid]["o"]))
        groups["strict"][(*base,ct["a"],ct["o"])].append(cid)
        groups["event_degree"][base].append(cid)
    return shape,groups,len(counters)
def cell_mapping(groups,seed,tid):
    assigned={}
    for group in groups.values():
        if len(group)<2:continue
        shuffled=sorted(group,key=lambda j:hashlib.sha256(f"{seed}|{tid}|{j}".encode("ascii")).digest())
        partners=shuffled[1:]+shuffled[:1]
        assert len(set(shuffled))==len(set(partners)) and all(a!=b for a,b in zip(shuffled,partners))
        assigned.update(zip(shuffled,partners))
    return assigned
def package(order,prefix,shape,mapping):
    def cell(node):
        cid,role,_=shape[node]
        return (mapping.get(cid,cid) if role=="o" else cid),role
    starts={cell(k) for k in prefix if shape[k][0]>=0}
    def priority(k):
        cid,role=cell(k)
        return (cid, "o" if role=="a" else "a") not in starts
    after=sorted(order[len(prefix):],key=priority)
    keep=list(prefix);remaining=2048-sum(shape[k][2] for k in keep)
    for k in after:
        c=shape[k][2]
        if c<=remaining:keep.append(k);remaining-=c
    return keep
def forecasts():
    check("placebo-plan.json")
    archive=load("placebo-event-metadata.json.gz")
    orig=load("forecast-lock.json")["forecasts"]
    receipt={"placebo-plan.json":pilot.sha(ROOT/"placebo-plan.json"),"placebo-event-metadata.json.gz":pilot.sha(ROOT/"placebo-event-metadata.json.gz")}
    for i in range(8):
        fname=f"forecasts-shard-{i}.jsonl.gz";assert pilot.sha(ROOT/fname)==orig[fname]
        predictions={}
        for rec in streamgz(ROOT/fname):
            t=rec["trajectory_id"];views=rec["queries"]
            first=next(iter(views.values()))["provenance"]["ranked"]
            shape,groups,n=make_groups(first,archive[t]);orders={}
            stat={mode:sum(len(x) for x in groups[mode].values() if len(x)>1) for mode in CONTROLS}
            pairs=sum(len(x) for x in groups["strict"].values())
            for mode in CONTROLS:orders[mode]=[cell_mapping(groups[mode],seed,t) for seed in SEEDS]
            nodekeys=sorted(shape);index={key:j for j,key in enumerate(nodekeys)}
            queries={}
            for q,v in views.items():
                pu=v["provenance"];rank=[x["node_id"] for x in pu["ranked"]];prefix=pu["arms"]["prefix"]
                assert set(rank)==set(nodekeys) and package(rank,prefix,shape,{})==pu["arms"]["related"]
                queries[q]={mode:[[index[k] for k in package(rank,prefix,shape,mp)[len(prefix):]] for mp in orders[mode]] for mode in CONTROLS}
            predictions[t]={"all_calls":n,"args_and_results":pairs,"rewired":stat,"queries":queries}
        dest=f"placebo-forecasts-{i}.json.gz"
        write(dest,predictions);receipt[dest]=pilot.sha(ROOT/dest)
        print("sealed placebo shard",i,flush=True)
    write("placebo-forecast-lock.json",receipt)
def cluster_ci(rows):
    groups=defaultdict(list)
    for t,delta in rows:groups[t].append(delta)
    arr=np.asarray([sum(a) for t,a in sorted(groups.items())])
    n=np.asarray([len(a) for t,a in sorted(groups.items())])
    rng=np.random.default_rng(13);dist=[]
    for _ in range(40):
        ids=rng.integers(0,len(n),size=(250,len(n)))
        dist.extend(arr[ids].sum(1)/n[ids].sum(1))
    return [float(x) for x in np.quantile(dist,[.025,.975])]
def joined():
    check("placebo-forecast-lock.json");check("placebo-plan.json")
    obs={r["q"]:r for r in load("outcomes.json.gz") if r["view"]=="provenance" and r["arm"]=="related"}
    gold=load("gold-spans.json.gz");rows=[];tstats={}
    for i in range(8):
        forecasts=load(f"placebo-forecasts-{i}.json.gz")
        for original in streamgz(ROOT/f"forecasts-shard-{i}.jsonl.gz"):
            t=original["trajectory_id"];pred=forecasts[t];tstats[t]={k:v for k,v in pred.items() if k!="queries"}
            for q,views in original["queries"].items():
                pu=views["provenance"];pool={n["node_id"]:n for n in pu["ranked"]};ids=sorted(pool);base=pu["arms"]["prefix"]
                full=tuple(pu["arms"]["related"]);native={key:val for key,val in obs[q].items() if key in ("full_support","coverage","density","tokens")}
                cache={}
                def score(selection):
                    if selection not in cache:
                        nodes=[pool[k] for k in selection];spans=[s for n in nodes for s in n["source_spans"]]
                        metrics=evaluate(gold[q],spans)
                        nativ=pilot.span_metrics_under_token_budget(tuple(pilot.RankedNodeRecord.model_validate(n) for n in nodes),tuple(pilot.SourceSpan.model_validate(s) for s in gold[q]),2048)
                        assert all(abs(x-getattr(nativ,field))<1e-12 for x,field in zip(metrics,("full_support","coverage","density"),strict=True))
                        tok=sum(n["token_count"] for n in nodes);assert tok<=2048
                        cache[selection]={**dict(zip(("full_support","coverage","density"),metrics,strict=True)),"tokens":tok}
                    return cache[selection]
                assert score(full)==native
                for mode in CONTROLS:
                    for seed,suffix in enumerate(pred["queries"][q][mode]):
                        selection=tuple(base+[ids[k] for k in suffix])
                        assert len(selection)==len(set(selection))
                        rows.append({"q":q,"t":t,"mode":mode,"seed":seed,"changed":set(selection)!=set(full),**score(selection)})
    assert len(rows)==2000*len(SEEDS)*len(CONTROLS)
    # Data for independent scoring are the two forecast archives, native source-coordinate spans and gold.
    return rows,tstats,obs
def old_ids():
    original=set();assigned=set();scored=set()
    for parent in (BASE,BASE/"replication"):
        meta=json.loads((parent/"cohort.json").read_bytes())
        for t,row in meta["selected"].items():
            original.add(t);assigned.update(row["queries"])
        rejected=set(json.loads((parent/"projection.json").read_bytes())["rejections"])
        scored.update(q for row in meta["selected"].values() for q in row["queries"] if q not in rejected)
    return original,assigned,scored
def summary():
    rows,tstats,obs=joined();old,assigned,scored=old_ids()
    found=set(q for q,r in obs.items() if r["t"] in old)
    overlap={"r17_trajectory_ids":len(old),"r17_assigned_queries":len(assigned),"r17_scored_queries":len(scored),"official_queries_with_r17_trajectory_id":len(found),"official_matches_r17_scored_ids":len(found&scored),"r17_scored_absent_official":len(scored-found),"official_on_r17_trajectory_absent_r17_scored":len(found-scored),"official_only_query_ids":sorted(found-scored)}
    out={"overlap":overlap}
    for label,times in (("all",set(tstats)),("no_previous_trajectories",set(tstats)-old)):
        actual={q:r for q,r in obs.items() if r["t"] in times}
        actual_full=sum(r["full_support"] for r in actual.values())
        per={}
        for mode in CONTROLS:
            panel=[r for r in rows if r["mode"]==mode and r["t"] in times]
            queries=defaultdict(list)
            for r in panel:queries[r["q"]].append(r["full_support"])
            assert set(queries)==set(actual) and all(len(a)==len(SEEDS) for a in queries.values())
            deltas=[(actual[q]["t"],actual[q]["full_support"]-statistics.mean(v)) for q,v in queries.items()]
            seeds=[]
            for seed in SEEDS:
                it=[r for r in panel if r["seed"]==seed]
                seeds.append(dict(seed=seed,full_count=int(sum(r["full_support"] for r in it)),wins=sum(actual[r["q"]]["full_support"]>r["full_support"] for r in it),losses=sum(actual[r["q"]]["full_support"]<r["full_support"] for r in it),changed=sum(r["changed"] for r in it),tokens=statistics.mean(r["tokens"] for r in it)))
            per[mode]={"real_full":int(actual_full),"per_seed":seeds,"n":len(actual),"trajectories":len(times),
                       "real_minus_mean_placebo":statistics.mean(v for _,v in deltas),"trajectory_bootstrap_ci95":cluster_ci(deltas),
                       "rewired_calls":sum(tstats[t]["rewired"][mode] for t in times),"all_calls":sum(tstats[t]["all_calls"] for t in times),
                       "all_two_sided_calls":sum(tstats[t]["args_and_results"] for t in times),"mean_changed_fraction":statistics.mean(r["changed"] for r in panel),
                       "placebo":{k:statistics.mean(r[k] for r in panel) for k in ("full_support","coverage","density","tokens")},
                       "real":{k:statistics.mean(r[k] for r in actual.values()) for k in ("full_support","coverage","density","tokens")}}
        out[label]=per
    write("placebo-results.json",out)
    print({key:{mode:out[key][mode]["real_minus_mean_placebo"] for mode in CONTROLS} for key in ("all","no_previous_trajectories")},flush=True)
    print(overlap,flush=True)
if __name__=="__main__":
    {"freeze":freeze,"metadata":metadata,"forecasts":forecasts,"summary":summary}[sys.argv[1]]()
