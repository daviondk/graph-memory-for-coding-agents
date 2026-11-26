from pathlib import Path
import importlib.util,json,hashlib,sys
from collections import defaultdict
from functools import lru_cache
D=Path(__file__).resolve().parent;W=D.parents[1];M=D.parent/"materialized_append";VIS=D.parent/"visibility_oracle"
def module(tag,p):
    spec=importlib.util.spec_from_file_location(tag,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
v=module("r36_visibility_terms",VIS/"study.py");base=module("r35_native_oracle",W/"graph_memory_round35/live_demo/oracle.py");l=v.l
def main():
    page=(D/"index.html").read_text(encoding="utf8");payload=json.loads(page.split('<script id="dataset" type="application/json">')[1].split('</script>')[0])
    inputs=l.read(D/"source.json");gold=l.read(l.ref.OFF/"gold-spans.json.gz");outcome={(r["q"],r["cut"]):r for r in l.read(M/"outcomes.json.gz")}
    tok=l.env.pilot.offsets(l.env.pilot.Tokenizer.from_file(str(l.env.pilot.CACHE/"tokenizer.json")));oracle={};n=0
    for c in payload["cases"]:
        q=c["q"];t=c["history"];sh=inputs["inputs"][q]["shard"]
        _,raw=next((b,r) for b,r in l.env.pilot.stream(l.env.RAW/f"trajectories-{sh:05d}.jsonl") if r["session_id"]==t)
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(raw),source_revision=l.env.pilot.RAW[1]);life=v.windows(tr.events)
        ranks={z[2]:z[3] for z in l.read(M/f"orders-{sh}.json.gz") if z[0]==q}
        real=tuple(base.RankedNodeRecord.model_validate(a) for a in next(z for z in l.read(l.ref.TR/f"forecasts-main-{sh}.json.gz") if z["q"]==q)["rr"])
        gs=tuple(base.SourceSpan.model_validate(z) for z in gold[q]);index={r.node_id:j for j,r in enumerate(real)}
        call={e.event_id:e.call_id for e in tr.events if e.event_type=="tool_output"};members=defaultdict(list)
        for j,r in enumerate(real):
            if r.node_id.startswith("output-content:"):members[call[r.source_spans[0].event_id]].append(j)
        def expand(pairs):return {(a,b,2) for p,r in pairs for a in members[p] for b in members[r]}
        @lru_cache(maxsize=None)
        def chunks(s):return l.env.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
        ever=set();by={};pcs=l.parent.cuts_for(tr.events)
        for j,e in enumerate(tr.events):
            if e.event_type!="tool_output":continue
            actual=v.native(tr,j);ever.update(actual);n+=1;z=v.sets(life,j);assert actual==z["E"] and ever==z["M"]
            if j not in pcs:continue
            for pct,pos in zip((25,50,75,100),pcs):
                if j!=pos:continue
                st=c["cuts"][str(pct)];active=expand(actual);once=expand(ever)-active;never=expand(z["L"])-expand(ever)
                assert active=={tuple(x) for x in st["edges"] if x[2]==2} and once==set(map(tuple,st["once"])) and never==set(map(tuple,st["never"]))
                view=tr.model_copy(update={"events":tr.events[:j+1],"source_metadata":None,"final_response":"","source_total_steps":j+1})
                full=l.parent.build_provenance_graph(view,content_chunker=chunks);ids,g=l.geometry({"g":full.model_dump()})
                assert {(index[a],index[b],k) for a,b,k in l.edges_by_name(ids,g)}==set(map(tuple,st["edges"]))
                state={"edges":{"active":sorted(active),"once":sorted(once),"never":sorted(never)},"modes":{}}
                for m in ("E","M","L"):
                    picks=ranks[pct][m][2];rr=tuple(real[k] for k in picks);met=base.span_metrics_under_token_budget(rr,gs,2048);got,total=base.intersect(rr,gs)
                    used=sum(r.token_count for r in rr);assert outcome[q,pct]["arms"][m]==[met.full_support,met.coverage,used,len(rr)] and abs(got/total-met.coverage)<1e-12
                    state["modes"][m]={"picks":picks,"used":used,"got":got,"total":total,"full":bool(met.full_support)}
                by[str(pct)]=state
        oracle[q]=by
    l.save(D/"ui-oracle.json",oracle);l.save(D/"oracle-receipt.json",{"full_prefixes":12,"output_prefixes":n,"policy_states":36,"code":l.sha(D/"oracle.py"),"source":l.sha(D/"source.json"),"oracle":l.sha(D/"ui-oracle.json")});print("verified",n,"native output prefixes, 36 policies",flush=True)
if __name__=="__main__":main()
