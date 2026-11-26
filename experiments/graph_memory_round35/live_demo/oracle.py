"""Check controls against signed native picks and build current graph afresh from each event prefix."""
from pathlib import Path
from functools import lru_cache
import json,sys,hashlib
D=Path(__file__).resolve().parent;W=D.parents[1];L=W/"graph_memory_round34/live_reader"
sys.path.insert(0,str(L));import live as l
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
def intersect(rr,gs):
    def flatten(items):
        out={}
        for r in items:out.setdefault((r.event_id,r.json_pointer),[]).append((r.char_start,r.char_end))
        for k,segments in out.items():
            merged=[]
            for a,b in sorted(segments):
                if merged and merged[-1][1]>=a:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
                else:merged.append((a,b))
            out[k]=merged
        return out
    g=flatten(gs);p=flatten([s for item in rr for s in item.source_spans])
    exact=sum(max(0,min(b,v)-max(a,u)) for k,ss in g.items() for a,b in ss for u,v in p.get(k,[]))
    return exact,sum(b-a for ss in g.values() for a,b in ss)
def main():
    markup=(D/"index.html").read_text(encoding="utf8")
    data=json.loads(markup.split('<script id="dataset" type="application/json">')[1].split('</script>')[0])
    meta=l.read(D/"source.json");gold=l.read(l.ref.OFF/"gold-spans.json.gz")
    vals={(o["q"],o["cut"]):o for o in l.read(L/"outcomes.json.gz")}
    tok=l.env.pilot.offsets(l.env.pilot.Tokenizer.from_file(str(l.env.pilot.CACHE/"tokenizer.json")))
    proofs={};counts=0
    for obj in data["cases"]:
        q=obj["q"];t=obj["history"];sh=meta["inputs"][q]["shard"];key=l.read(L/f"forecast-{sh}.json.gz")
        forecasts={z["cut"]:z["selected"] for z in key if z["q"]==q};one=next(r for r in l.read(l.ref.TR/f"forecasts-main-{sh}.json.gz") if r["q"]==q)
        actual=tuple(RankedNodeRecord.model_validate(r) for r in one["rr"]);orig={v.node_id:i for i,v in enumerate(actual)}
        for i,node in enumerate(actual):
            assert hashlib.sha256(node.node_id.encode()).hexdigest()[:12]==obj["nodes"][i]["hash"]
        target=tuple(SourceSpan.model_validate(z) for z in gold[q])
        rb,raw=next((rb,r) for rb,r in l.env.pilot.stream(l.env.RAW/f"trajectories-{sh:05d}.jsonl") if r["session_id"]==t)
        assert hashlib.sha256(rb).hexdigest()==meta["inputs"][q]["raw_record"]
        traj=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(raw),source_revision=l.env.pilot.RAW[1])
        @lru_cache(maxsize=None)
        def chunks(s):return l.env.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
        by={};old=set()
        for pct,step in zip((25,50,75,100),l.parent.cuts_for(traj.events)):
            sl=obj["cuts"][str(pct)];assert sl["step"]==step+1
            trunc=traj.model_copy(update={"events":traj.events[:step+1],"source_metadata":None,"final_response":"","source_total_steps":step+1})
            graph=l.parent.build_provenance_graph(trunc,content_chunker=chunks)
            ids,arr=l.geometry({"g":graph.model_dump()});edges={(orig[a],orig[b],k) for a,b,k in l.edges_by_name(ids,arr)}
            assert edges==set(map(tuple,sl["edges"])) and set(orig[n] for n in ids)==set(sl["alive"])
            stale=set(map(tuple,sl["stale"]));assert not stale&edges and all(a in sl["alive"] and b in sl["alive"] and k==2 for a,b,k in stale)
            comparisons={"changed":{"added":len(edges-old),"removed":len(old-edges),"stale":len(stale)}}
            old=edges
            for m in ("exact","append"):
                picked=forecasts[pct][m][2];ranked=tuple(actual[j] for j in picked);z=span_metrics_under_token_budget(ranked,target,2048)
                got,total=intersect(ranked,target);spent=sum(n.token_count for n in ranked);rec=vals[q,pct]["arms"][m]
                assert abs(got/total-z.coverage)<1e-12 and z.full_support==(got==total)
                assert list(rec[:2])==[z.full_support,z.coverage] and spent==rec[4]
                comparisons[m]={"picks":picked,"used":spent,"got":got,"total":total,"full":bool(z.full_support)}
                counts+=1
            by[str(pct)]=comparisons
        proofs[q]=by
    assert counts==24 and len(proofs)==3
    l.save(D/"ui-oracle.json",proofs);l.save(D/"oracle-receipt.json",{"program":l.sha(Path(__file__)),"oracle":l.sha(D/"ui-oracle.json"),"source":l.sha(D/"source.json"),"fresh_prefix_graphs":12,"query_cut_policy":counts})
    print("Validated",counts,"policy states and 12 fresh prefix graphs",flush=True)
if __name__=="__main__":main()
