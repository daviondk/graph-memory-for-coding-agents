"""Describe event coverage, acknowledged mutations, and explicit run termination. Treat payloads as data."""
from pathlib import Path
import sys,json,gzip
from collections import defaultdict,Counter
D=Path(__file__).resolve().parent
V=D.parent/"code_visibility";S=D.parent/"code_store"
prior=D.parents[1]/"graph_memory_round31/natural_handoff";sys.path.insert(0,str(prior))
from source import cohort,REV,P,OLD,pq,get,save,sha,h
from extract import norm

def build():
    assert sha(V/"manifest.json")=="4ae0456b82d9c53d506a329f3882f202c2d99b7461580349a9c7f1a000e9b27f"
    assert sha(S/"manifest.json")=="20caf717a4076477487d4b870c9a20d35bbdf48c5e562e4fff6422506d90aaeb"
    rr,_=cohort();meta={}
    for p in OLD.glob("data-*.parquet"):
        for row in pq.read_table(p,columns=["run_id","has_run_error","agent_events"]).to_pylist():
            if row["run_id"] in rr:meta[row["run_id"]]=row
    ids=defaultdict(list);acts=defaultdict(dict);obs=defaultdict(dict);tail={};bad=defaultdict(set);src=get(P/"files.json")["events"]
    for ref in src:
        p=P/ref["file"];assert sha(p)==ref["sha"]
        for b in pq.ParquetFile(p).iter_batches(columns=["run_id","event_type","event_index","source_json_valid","event_json"],batch_size=512):
            names=b.column("run_id").to_pylist();types=b.column("event_type").to_pylist();idxs=b.column("event_index").to_pylist();val=b.column("source_json_valid").to_pylist()
            for j,(rid,typ,i) in enumerate(zip(names,types,idxs)):
                if rid not in rr:continue
                ids[rid].append(i)
                if typ not in ("ActionEvent","ObservationEvent"):continue
                tail[rid]=max(tail.get(rid,-1),i)
                if not val[j]:bad[rid].add(i);continue
                raw=json.loads(b.column("event_json")[j].as_py()).get("raw",{})
                isact=typ=="ActionEvent";x=raw.get("action" if isact else "observation",{})
                kind=x.get("kind");key=raw.get("id" if isact else "action_id")
                if not key:continue
                if kind in ("FinishAction","FinishObservation"):cmd,path="finish",None
                elif kind in ("FileEditorAction","FileEditorObservation") and x.get("command")!="view" and norm(x.get("path")):
                    cmd,path=x["command"],norm(x["path"])
                else:continue
                store=acts[rid] if isact else obs[rid]
                assert key not in store
                store[key]=(i,cmd,path,raw.get("tool_call_id"),bool(x.get("is_error")))
    out={};stats=Counter()
    for rid,run in rr.items():
        points=sorted(ids[rid]);assert points==sorted(set(points))
        gaps=[(a,b) for a,b in zip(points,points[1:]) if b!=a+1]
        if not points:
            out[h(rid)]=dict(empty=True);continue
        pairs=[];finished=None
        for key,(i,cmd,path,tid,_) in acts[rid].items():
            ob=obs[rid].get(key)
            if ob and ob[0]>i and ob[1:4]==(cmd,path,tid) and not ob[4]:
                j=ob[0]
                if cmd=="finish":
                    stats["matched_finish_calls"]+=1
                    if j==tail[rid] and meta[rid]["has_run_error"] is False:finished=j
                else:pairs.append([i,j,cmd,h(path)])
        if finished is not None:stats["verified_finished_runs"]+=1
        stats["runs_with_unresolved_terminal_tail"]+=finished is None
        stats["runs_with_index_gaps"]+=bool(gaps)
        stats["runs_with_invalid_action_observation"]+=bool(bad[rid])
        stats["run_errors"]+=bool(meta[rid]["has_run_error"])
        out[h(rid)]=dict(first=points[0],last=points[-1],last_interaction=tail.get(rid),rows=len(points),gaps=gaps,
            reported_events=meta[rid]["agent_events"],run_error=meta[rid]["has_run_error"],finished=finished,successful_writes=sorted(pairs))
    f=save(D/"native_boundaries.json.gz",out)
    save(D/"boundary-seal.json",dict(data=f,code=sha(Path(__file__)),revision=REV,files=sha(P/"files.json"),protocol=sha(D/"PROTOCOL_RU.md"),
       previous_visibility=sha(V/"manifest.json"),previous_store=sha(S/"manifest.json"),stats=stats))
    print(dict(stats))
if __name__=="__main__":build()
