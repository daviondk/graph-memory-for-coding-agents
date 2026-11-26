"""Use the pinned native graph constructor on every output prefix in the independent hash sample."""
from materialize import *
from functools import lru_cache
def main():
    p=load(D/"plan.json");targets=set(p["audit_ids"]);assert len(targets)==12;tok=l.env.pilot.offsets(l.env.pilot.Tokenizer.from_file(str(l.env.pilot.CACHE/"tokenizer.json")));allout={}
    for sh in range(8):
        ref=load(l.ref.TR/f"forecasts-main-{sh}.json.gz");want=targets&{r["t"] for r in ref}
        if not want:continue
        raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl";assert sha(raw)==load(R34/"plan.json")["raw"][raw.name]
        for _,obj in l.env.pilot.stream(raw):
            t=obj["session_id"]
            if t not in want:continue
            tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
            @lru_cache(maxsize=None)
            def chunks(s):return l.env.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
            done=set();union=set();states=[];incomplete=0
            for step,event in enumerate(tr.events):
                if event.event_type!="tool_output":continue
                done.add(event.call_id);prefix=tuple(e for e in tr.events[:step+1] if e.event_type!="tool_call" or e.call_id in done)
                incomplete+=len(prefix)!=step+1
                subset=tr.model_copy(update={"events":prefix,"source_metadata":None,"final_response":"","source_total_steps":step+1})
                graph=l.parent.build_provenance_graph(subset,content_chunker=chunks);ids,g=l.geometry({"g":graph.model_dump()})
                pairs={(a,b) for a,b,k in l.edges_by_name(ids,g) if k==2};union|=pairs
                # Independent serialization from the canonical pair relation.
                digest=lambda s:hashlib.sha256(json.dumps(sorted([a,b] for a,b in s),separators=(",",":")).encode("ascii")).hexdigest()
                states.append([step,len(pairs),digest(pairs),len(union),digest(union)])
            allout[t]=dict(states=states,incomplete=incomplete)
        print("native shard",sh,len(allout),flush=True)
    assert set(allout)==targets;put(D/"native-raw-states.json.gz",allout)
def compare():
    p=D/"native-raw-states.json.gz";a=load(p);wanted=set(load(D/"plan.json")["audit_ids"]);streamed={}
    for i in range(8):streamed.update(load(D/f"sample-{i}.json.gz"))
    assert set(a)==set(streamed)==wanted
    for t in a:assert a[t]["states"]==streamed[t],t
    put(D/"native-audit.json",dict(trajectories=len(wanted),tool_output_prefixes=sum(len(v["states"]) for v in a.values()),prefixes_with_temporarily_unmatched_calls=sum(v["incomplete"] for v in a.values()),
        pairset_digests_checked=2*sum(len(v["states"]) for v in a.values()),source=sha(p),plan=sha(D/"plan.json"),code=sha(Path(__file__))))
if __name__=="__main__":
    if sys.argv[1]=="build":main()
    else:compare()