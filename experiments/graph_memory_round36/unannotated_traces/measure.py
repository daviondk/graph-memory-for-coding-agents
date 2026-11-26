"""Replay full traces without question text or labels. Corpus events are passive JSON data."""
from panel import *
import os,sys
for var in ("MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","OMP_NUM_THREADS"):os.environ[var]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
sys.path.insert(0,str(R));import live as l
sys.path.insert(0,str(SW));from reader import HistoricalFeeds
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
from graph_memory.datasets.isetrace.adapter import ISETraceAdaptationError
from pydantic import ValidationError
PCTS=(25,50,75,100)
def address_pairs(edges,groups):
    return {(x,y) for a,b in edges for x in groups.get(a,()) for y in groups.get(b,())}
def edgehash(p):
    return digest(json.dumps(sorted(p),separators=(",",":")))
def projected(graph):
    ids,packed=l.geometry({"g":graph.model_dump()}); names=list(ids);members=defaultdict(list)
    for i,g in enumerate(packed.membership):members[int(g)].append(names[i])
    return {(a,b) for x,y,k in packed.links if k==2 for a in members[x] for b in members[y]}
def one(obj,t,native,tok):
    try:tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
    except ISETraceAdaptationError as e:return {"status":"unsupported_adapter_"+e.code}
    except ValidationError as e:return {"status":"unsupported_schema","error_types":sorted({x["type"] for x in e.errors()})}
    events=tr.events; calls=[];outs=[];pending=set();parallel=False;allids=set()
    for ev in events:
        if ev.event_type=="tool_call":
            if ev.call_id in allids:return {"status":"duplicate_call"}
            allids.add(ev.call_id);calls.append(ev.call_id);pending.add(ev.call_id);parallel|=len(pending)>1
        elif ev.event_type=="tool_output":
            if ev.call_id not in pending:return {"status":"unmatched_output"}
            pending.remove(ev.call_id);outs.append(ev.call_id)
    if not calls:return {"status":"no_tool_calls"}
    if pending:return {"status":"unclosed_tool_calls","open":len(pending),"completed":len(outs)}
    @lru_cache(maxsize=2048)
    def chunks(text):return l.env.pilot.token_chunks(text,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    graph=l.parent.build_provenance_graph(tr,content_chunker=chunks);groups=defaultdict(list)
    for n in graph.nodes:
        if n.kind==l.ref.OUTPUT_CHUNK_NODE:groups[n.attributes["call_id"]].append(n.node_id)
    native_final=projected(graph);cuts=l.parent.cuts_for(events);seen=set();members=set();open_ids=set();past=set();states={};native_log=[];hist=set();nc=0;unfinished=0;checks=0;peak_old=0;peak_open=0;total_old=0;total_open=0
    idx=l.FeedIndex();online=HistoricalFeeds()
    for step,e in enumerate(events):
        if e.event_type not in ("tool_call","tool_output"):continue
        idx.consume(e);output=e.event_type=="tool_output";online.consume(e,output and bool(groups.get(e.call_id)))
        if output:
            open_ids.remove(e.call_id);seen.add(e.call_id)
            if groups.get(e.call_id):members.add(e.call_id)
        else:open_ids.add(e.call_id)
        cur={p for p in idx.support if p[0] in members and p[1] in members};past.update(cur);checks+=1
        assert online.observed_pairs==past and online.visible_outputs==members,(t,step)
        old=sum(len(k.readers) for k in idx.values.values() if k is not None);new=online.pending_references();peak_old=max(peak_old,old);peak_open=max(peak_open,new);total_old+=old;total_open+=new
        if native and output:
            prefix=tuple(ev for ev in events[:step+1] if ev.event_type!="tool_call" or ev.call_id in seen);unfinished+=int(len(prefix)!=step+1)
            view=tr.model_copy(update={"events":prefix,"source_metadata":None,"final_response":"","source_total_steps":step+1})
            active=projected(l.parent.build_provenance_graph(view,content_chunker=chunks));hist.update(active)
            assert active==address_pairs(cur,groups) and hist==address_pairs(past,groups),(t,step)
            native_log.append([step,len(active),edgehash(active),len(hist),edgehash(hist)]);nc+=1
        if step in cuts:
            logical={p for p in idx.ever if p[0] in members and p[1] in members};assert cur<=past<=logical
            def packed(edges):return sum(len(groups[a])*len(groups[b]) for a,b in edges)
            scopes=[cur,past,logical,past-cur,logical-past]; row={"pu":[packed(v) for v in scopes],"groups":[len(v) for v in scopes],"step":step}
            for pct,cut in zip(PCTS,cuts):
                if cut==step:states[str(pct)]=row
    assert set(states)==set(map(str,PCTS)) and not online.open_calls and not open_ids and native_final==address_pairs(cur,groups)
    return {"status":"retained","calls":len(calls),"outputs":len(outs),"event_checks":checks,"distinct_cuts":len(set(cuts)),"cuts":states,"output_units":sum(map(len,groups.values())),"empty_outputs":sum(not groups.get(o) for o in outs),"parallel":parallel,
        "memory":[peak_old,peak_open,total_old,total_open],"native_prefixes":nc,"incomplete_native":unfinished,"native_states":native_log}
def shard(sh):
    plan=load(D/"plan.json");f=RAW/"trajectories"/f"trajectories-{sh:05d}.jsonl";subset=[(t,z) for t,z in plan["panel"].items() if z[0]==sh];subset.sort(key=lambda x:x[1][1]);native=set(plan["native"]);out={};tok=l.env.pilot.offsets(l.env.pilot.Tokenizer.from_file(str(l.env.pilot.CACHE/"tokenizer.json")))
    with f.open("rb") as src:
        for t,(shardno,pos,n) in subset:
            src.seek(pos);b=src.read(n);obj=json.loads(b);assert obj["session_id"]==t;z=one(obj,t,t in native,tok);z["record_sha"]=hashlib.sha256(b).hexdigest();out[t]=z
    p=D/f"histories-{sh}.json.gz";save(p,out);print("shard",sh,len(out),sum(r["status"]=="retained" for r in out.values()),flush=True);return p.name,sha(p)
def main():
    p=load(D/"plan.json");assert sha(P/"manifest.json")==p["r36"] and sha(SW/"manifest.json")==p["streaming"] and sha(D/"PROTOCOL_RU.md")==p["protocol"]
    frozen={"panel":sha(D/"plan.json"),"program":sha(D/"measure.py"),"native_chunker":sha(l.env.pilot.CACHE/"tokenizer.json"),"streaming_operator":sha(SW/"reader.py")};save(D/"run-plan.json",frozen)
    with ProcessPoolExecutor(max_workers=2) as pool: hashes=dict(pool.map(shard,range(8)))
    save(D/"run-seal.json",{"plan":sha(D/"run-plan.json"),"parts":hashes})
if __name__=="__main__":main()
