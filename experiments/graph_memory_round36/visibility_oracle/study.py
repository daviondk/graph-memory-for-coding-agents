"""Independent interval-based reconstruction. Only structural summaries leave each case."""
import os
for n in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[n]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import sys,json,hashlib,gzip
from pathlib import Path
from collections import defaultdict,Counter
D=Path(__file__).resolve().parent;WORK=D.parents[1];R34=WORK/"graph_memory_round34/live_reader";sys.path.insert(0,str(R34))
import live as l
from graph_memory.graphs.provenance.builder import _typed_tokens,_argument_contains
from graph_memory.trajectories import ToolCallEvent,ToolOutputEvent,SourcePosition
from types import SimpleNamespace
def digest(x):return hashlib.sha256(x.encode()).hexdigest()
def windows(events):
    infinity=len(events)+1;values={};outputs={};calls={}
    for time,e in enumerate(events):
        if e.event_type=="tool_call":
            assert e.call_id not in calls;calls[e.call_id]=time
        elif e.event_type=="tool_output":
            assert e.call_id not in outputs;outputs[e.call_id]=time
            for _,val in _typed_tokens(e.content):
                entry=values.setdefault(val,[e.call_id,time,infinity])
                if e.call_id!=entry[0]:entry[2]=min(entry[2],time)
    assert set(outputs)==set(calls) and all(calls[k]<outputs[k] for k in calls)
    witness=defaultdict(list)
    for reader,c in calls.items():
        e=events[c]
        for word,(writer,begin,end) in values.items():
            if begin<c<end and _argument_contains(e,word):witness[writer,reader].append(end)
    return {k:(outputs[k[1]],max(end),min(end),len(end)) for k,end in witness.items()}
def sets(life,T):
    logical={p for p,(o,_,_,_) in life.items() if o<=T}
    mat={p for p in logical if life[p][1]>life[p][0]}
    exact={p for p in logical if life[p][1]>T}
    on={p for p in logical if life[p][1]==life[p][0]};before=logical-mat-on
    assert exact<=mat<=logical and all(life[p][1]<life[p][0] for p in before)
    return dict(E=exact,M=mat,L=logical,equal_boundary=on,before_boundary=before,revoked_materialized=mat-exact,
                multiple_with_early_loss={p for p in mat if life[p][2]<=life[p][0]})
def pair_h(s):return digest(json.dumps(sorted(s),separators=(",",":")))
def native(tr,time):
    done={e.call_id for e in tr.events[:time+1] if e.event_type=="tool_output"}
    prefix=tuple(e for e in tr.events[:time+1] if e.event_type!="tool_call" or e.call_id in done)
    sub=tr.model_copy(update={"events":prefix,"source_metadata":None,"final_response":"","source_total_steps":time+1})
    graph=l.parent.build_provenance_graph(sub,artifact_extractors=())
    return {(e.source.removeprefix("output:"),e.target.removeprefix("call:")) for e in graph.edges if e.relation==l.ref.FEEDS_EDGE}
def case(tr,n_units,extra):
    win=windows(tr.events);cuts=l.parent.cuts_for(tr.events);checks=0;observed=set()
    if extra:
        for time,e in enumerate(tr.events):
            if e.event_type=="tool_output":
                direct=native(tr,time);observed.update(direct);z=sets(win,time)
                assert direct==z["E"] and observed==z["M"],(time,len(direct),len(z["E"]))
                checks+=1
    by={};out={e.call_id:n_units[e.event_id] for e in tr.events if e.event_type=="tool_output"}
    for pct,t in zip((25,50,75,100),cuts):
        z=sets(win,t);by[pct]={"call_pairs":{k:len(v) for k,v in z.items()},"pu_pairs":{k:sum(out[a]*out[b] for a,b in v) for k,v in z.items()},
                             "identities":{k:pair_h(v) for k,v in z.items()}}
    return by,checks
def fabricated(tr):
    a,b="alpha_fixture.csv","beta_fixture.csv"
    patterns={
      "at_visibility":[("c","a",""),("o","a",a),("c","b",a),("o","b",a)],
      "before_visibility":[("c","a",""),("o","a",a),("c","b",a),("c","x",""),("o","x",a),("o","b","neutral")],
      "after_visibility":[("c","a",""),("o","a",a),("c","b",a),("o","b","neutral"),("c","x",""),("o","x",a)],
      "surviving_witness":[("c","a",""),("o","a",a+" "+b),("c","b",a+" "+b),("o","b",a)]}
    expect={"at_visibility":(False,False,True,True,False),"before_visibility":(False,False,True,False,True),
            "after_visibility":(False,True,True,False,False),"surviving_witness":(True,True,True,False,False)}
    results={}
    for typ,pattern in patterns.items():
        events=[]
        for j,(kind,uid,v) in enumerate(pattern):
            pos=SourcePosition(message_index=j,sub_index=0);kw=dict(event_id=f"synthetic-{j}",position=pos,call_id=uid,tool_name="fixture")
            events.append(ToolCallEvent(**kw,arguments={"input":v},raw_arguments=json.dumps({"input":v})) if kind=="c" else ToolOutputEvent(**kw,content=v))
        fake=tr.model_copy(update={"events":tuple(events),"source_metadata":None,"final_response":""});w=windows(events);observed=set()
        for time,e in enumerate(events):
            if e.event_type=="tool_output":
                direct=native(fake,time);observed.update(direct);z=sets(w,time)
                assert z["E"]==direct and z["M"]==observed
        z=sets(w,len(events)-1);flags=tuple(("a","b") in z[k] for k in ("E","M","L","equal_boundary","before_boundary"))
        assert flags==expect[typ] and (len(w)==1)
        results[typ]=list(flags)
    return results
def main():
    split=l.read(l.ref.TR/"split.json.gz")["test"];ts={r["t"] for r in split}
    sample=set(sorted(ts,key=lambda t:digest("R36-visibility-oracle/"+t))[:16]);assert len(ts)==1207
    plan={"native_sample":sorted(sample),"protocol":l.sha(D/"PROTOCOL_RU.md"),"code":l.sha(D/"study.py"),"r34":l.sha(R34/"manifest.json")}
    if (D/"plan.json").exists():assert plan==l.read(D/"plan.json")
    else:l.save(D/"plan.json",plan)
    by={};synthetic=None;nativechecks={}
    for sh in range(8):
        ranks=l.read(l.ref.TR/f"forecasts-main-{sh}.json.gz");bytraj={}
        for r in ranks:
            if r["t"] not in bytraj:bytraj[r["t"]]=Counter(n["source_spans"][0]["event_id"] for n in r["rr"] if n["node_id"].startswith("output-content:"))
        for _,obj in l.env.pilot.stream(l.env.RAW/f"trajectories-{sh:05d}.jsonl"):
            t=obj["session_id"]
            if t not in bytraj:continue
            tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
            if synthetic is None:synthetic=fabricated(tr)
            data,n=case(tr,bytraj[t],t in sample);assert t not in by;by[t]=data
            if n:nativechecks[t]=n
        print("shard",sh,len(by),flush=True)
    assert set(by)==ts and set(nativechecks)==sample
    summed={}
    for pct in (25,50,75,100):
        g={}
        for unit in ("call_pairs","pu_pairs"):
            tally=Counter()
            for b in by.values():tally.update(b[pct][unit])
            assert tally["L"]-tally["M"]==tally["equal_boundary"]+tally["before_boundary"]
            assert tally["M"]-tally["E"]==tally["revoked_materialized"];g[unit]=dict(tally)
        summed[pct]=g
    l.save(D/"histories.json.gz",by);l.save(D/"results.json",{"sums":summed,"histories":len(by),"native_prefixes":nativechecks,"n_prefix":sum(nativechecks.values()),
        "synthetic":synthetic,"units":l.sha(D/"histories.json.gz"),"plan":l.sha(D/"plan.json")})
    print("Completed interval oracle",sum(nativechecks.values()),summed[50]["pu_pairs"],flush=True)
if __name__=="__main__":main()
