"""Load official labels only after all forecasts have been saved and compared with history."""
import inspect
import shutil
import sys
from common import D,W,SEEDS,read,sha,put
assert all((D/f"forecast-{s}.json").exists() for s in SEEDS)
R39=W/"graph_memory_round39/hybrid_controls"
R43=W/"graph_memory_round43/metric_matched"
sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
import data as upstream

def main():
    pilot=upstream.nm.pilot
    source=upstream.nm.OFF/"gold-spans.json.gz"
    atoms_path=W/"graph_memory_round34/interval_witness/test-atoms.json.gz"
    gold,axis=read(source),read(atoms_path)
    signer=read(R39/"test-13-score-seal.json")
    assert sha(source)==signer["gold"] and sha(atoms_path)==signer["atoms"]
    sc=Path(inspect.getsourcefile(pilot.span_metrics_under_token_budget))
    assert sha(sc)==signer["scorer"]
    arch2={r[0]:r[2] for r in read(R43/"scores.json.gz")}
    arch1={s:read(R39/f"test-{s}-outcomes.json.gz") for s in SEEDS}
    plans={}
    for s in SEEDS:
        p=D/f"predictions-{s}.json.gz"
        assert sha(p)==read(D/f"forecast-{s}.json")["predictions"]
        plans[s]=read(p)
    rows={};calls=0
    for shard in upstream.sources("test"):
        for r in read(shard):
            q,t=r["q"],r["t"]
            nodes=[pilot.RankedNodeRecord.model_validate(x) for x in r["rr"]]
            refs=tuple(pilot.SourceSpan.model_validate(x) for x in gold[q])
            segments=[(b-a,set(ids)) for _,a,b,ids in axis[q]]
            length=sum(w for w,_ in segments);memo={};sr=[]
            for s in SEEDS:
                arm=[]
                for checkpoint,preds in enumerate(plans[s][q]):
                    res=[]
                    for i,ids in enumerate(preds):
                        # All packets fit, so coverage is invariant to their output order.
                        key=tuple(ids)
                        if key not in memo:
                            got=tuple(nodes[i] for i in ids)
                            cost=sum(x.token_count for x in got); assert cost<=2048
                            val=pilot.span_metrics_under_token_budget(got,refs,2048)
                            covered=sum(w for w,x in segments if not x.isdisjoint(ids))
                            assert abs(val.coverage-covered/length)<1e-12 and val.full_support==(covered==length)
                            memo[key]=[int(val.full_support),float(val.coverage),cost]
                        v=memo[key]
                        if checkpoint:
                            name=("dp","dp","dp","firstfit","value")[i]
                            prior=arch2[q][str(s)]["wo_chunk_adjacency/"+name]
                        else:
                            name=("graph_dp","graph_dp","graph_dp","firstfit","graph_value")[i]
                            prior=arch1[s][q][1]["wo_chunk_adjacency/"+name][1][3][:3]
                        assert v[0]==prior[0] and abs(v[1]-prior[1])<1e-12 and v[2]==prior[2]
                        res.append(v)
                    arm.append(res)
                sr.append(arm)
            calls+=len(memo);rows[q]=[t,sr]
    assert len(rows)==2000 and len(set(r[0] for r in rows.values()))==1207
    put(D/"scores.json.gz",rows)
    shutil.copyfile(atoms_path,D/"test-atoms.json.gz")
    put(D/"score_receipt.json",{"official_source":sha(sc),"official_gold":sha(source),"atoms":sha(atoms_path),"unique_ordered_official_calls":calls,"historical_metric_checks":100000,"scores":sha(D/"scores.json.gz")})
    print("official unique calls",calls,flush=True)
if __name__=="__main__":
    from pathlib import Path
    main()
