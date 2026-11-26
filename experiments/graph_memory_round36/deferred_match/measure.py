from common_match import *
from concurrent.futures import ProcessPoolExecutor
def run(sh):
    hist={};base=load(P/f"histories-{sh}.json.gz");plan=load(D/"plan.json")
    for t,events,chunks,geometry in rows(sh):
        cnt=Counter();argcost={};op=eager.HistoricalFeeds();pending={};evset={};checked={}
        orig=eager._argument_contains
        def query_baseline(e,value):
            cnt["predicate_old"]+=1;return orig(e,value)
        def query_new(e,value):
            cnt["predicate_new"]+=1;return orig(e,value)
        def get(h):
            cnt["lookups"]+=1;r,s=argcost[h];cnt["lookup_raw_bytes"]+=r;cnt["lookup_structured_bytes"]+=s;return events[h]
        later=DeferredFeeds(get,query_new);eager._argument_contains=query_baseline
        try:
            cuts=l.parent.cuts_for(events)
            for i,e in enumerate(events):
                if e.event_type not in ("tool_call","tool_output"):continue
                output=e.event_type=="tool_output";has=output and chunks[e.call_id]>0
                if not output:
                    raw,parsed=args_wire(e);sizes=(len(raw.encode()),len(parsed.encode()));argcost[i]=sizes
                    for label,val in zip(("all_raw_bytes","all_structured_bytes"),sizes):cnt[label]+=val
                    cnt["calls"]+=1;cnt["scanned_old"]+=len(op.producer);pos=(e.position.message_index,e.position.sub_index)
                    candidates=[v for v in op.producer.values() if v is not None and v[1]<pos];vis=sum(v[0] in op.visible_outputs for v in candidates)
                    pending[e.call_id]=(len(candidates),vis,pos,i)
                start=cnt["predicate_new"];op.consume(e,has);later.consume(e,i,has)
                assert op.producer==later.producer and op.visible_outputs==later.visible_outputs and op.observed_pairs==later.observed_pairs
                assert set(op.open_calls)==set(later.pending)
                if output:
                    eligible,vis,cp,h=pending.pop(e.call_id);assert h<i
                    used=cnt["predicate_new"]-start;assert 0<=used<=vis
                    if not has:cnt["zero_target_saved"]+=eligible
                    else:
                        cnt["scanned_new"]+=len(later.producer);cnt["invisible_source_saved"]+=eligible-vis;cnt["collision_saved"]+=vis-used
                    cnt["outputs"]+=1
                nw=op.pending_references();n=len(later.pending);cnt["peak_witnesses"]=max(cnt["peak_witnesses"],nw);cnt["peak_arg_handles"]=max(cnt["peak_arg_handles"],n)
                cnt["integral_witnesses"]+=nw;cnt["integral_arg_handles"]+=n;cnt["event_checks"]+=1;cnt["observed_identity_integral"]+=len(later.observed_pairs)
                for tag,step in zip(("25","50","75","100"),cuts):
                    if step!=i:continue
                    expect=geometry["states"][tag];npu=sum(chunks[a]*chunks[b] for a,b in later.observed_pairs)
                    assert npu==expect["material"] and len(later.observed_pairs)==expect["logical_pairs"]["M"]
                    checked[tag]=[len(later.observed_pairs),npu]
            assert cnt["predicate_old"]-cnt["predicate_new"]==cnt["zero_target_saved"]+cnt["invisible_source_saved"]+cnt["collision_saved"]
            assert cnt["peak_witnesses"]==base[t]["peak_open"] and cnt["integral_witnesses"]==base[t]["sum_open"]
            assert cnt["event_checks"]==base[t]["steps"] and cnt["observed_identity_integral"]==base[t]["checked_live_pairs"] and not later.pending and not pending
        finally:eager._argument_contains=orig
        hist[t]=dict(counts=dict(cnt),cuts=checked,final_pairs=len(later.observed_pairs))
    p=D/f"counters-{sh}.json.gz";put(p,hist);print("counted",sh,len(hist),flush=True);return p.name,sha(p)
def main():
    with ProcessPoolExecutor(2) as pool:files=dict(pool.map(run,range(8)))
    put(D/"counter-seal.json",dict(files=files,plan=sha(D/"plan.json"),code=sha(Path(__file__))))
if __name__=="__main__":seal_plan();main()