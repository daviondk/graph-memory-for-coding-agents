"""Score prefix selections, including eligibility under the visible source pool."""
from collections import defaultdict
from forecast import HERE,PREV,ref,save,np
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
from score_readout import paired

def run():
    lock=ref.read(HERE/"forecast-lock.json")
    assert lock["plan"]==ref.sha(HERE/"forecast-plan.json")
    gold=ref.read(ref.OFF/"gold-spans.json.gz")
    old={r["q"]:r for r in ref.read(PREV/"incremental_binding/readout-outcomes.json.gz")}
    results=[];contrasts=(("exact","final"),("exact","append"),("exact","dense"))
    for k in range(8):
        inputs=ref.read(ref.TR/f"forecasts-main-{k}.json.gz")
        nodes={r["q"]:[RankedNodeRecord.model_validate(n) for n in r["rr"]] for r in inputs}
        fp=HERE/f"forecast-{k}.json.gz";assert ref.sha(fp)==lock["files"][fp.name]
        for row in ref.read(fp):
            q=row["q"];rr=nodes[q];gs=tuple(SourceSpan.model_validate(g) for g in gold[q])
            visible=tuple(rr[j] for j in row["available"])
            vmax=span_metrics_under_token_budget(visible,gs,sum(n.token_count for n in visible))
            choices=row["selected"];outcomes={};cached={}
            for arm,indices in choices.items():
                assert set(indices)<=set(row["available"]);ids=tuple(indices)
                if ids not in cached:
                    subset=tuple(rr[j] for j in ids);tokens=sum(n.token_count for n in subset)
                    assert tokens<=2048
                    m=span_metrics_under_token_budget(subset,gs,2048)
                    cached[ids]=dict(fs=int(m.full_support),coverage=m.coverage,density=m.density,tokens=tokens)
                outcomes[arm]=cached[ids]
                assert outcomes[arm]["coverage"]<=vmax.coverage+1e-12
            if row["cut"]==100:
                assert all(outcomes[arm]==old[q]["arms"][arm] for arm in ("exact","append"))
            differences={a+"/"+b:choices[a]!=choices[b] for a,b in contrasts}
            results.append(dict(q=q,t=row["t"],cut=row["cut"],pilot=row["pilot"],eligible=bool(vmax.full_support),
                visible=vmax.coverage,n_visible=len(visible),arms=outcomes,different=differences))
        print("eval",k,len(results),flush=True)
    assert len(results)==8000 and len({(r["q"],r["cut"]) for r in results})==8000
    save(HERE/"outcomes.json.gz",results)
    panels={}
    for cut in (25,50,75,100):
        for sample in ("confirmatory","all"):
            for which in ("eligible","any"):
                rows=[r for r in results if r["cut"]==cut and (sample=="all" or not r["pilot"]) and (which=="any" or r["eligible"])]
                n=len(rows)
                panels[f"{cut}/{sample}/{which}"]=dict(n=n,trajectories=len({r["t"] for r in rows}),
                    summary={a:{"hits":sum(r["arms"][a]["fs"] for r in rows),"coverage":float(np.mean([r["arms"][a]["coverage"] for r in rows]))} for a in rows[0]["arms"]},
                    contrasts={a+"/"+b:paired(rows,a,b) for a,b in contrasts})
    save(HERE/"results.json",{"panels":panels,"outcomes":ref.sha(HERE/"outcomes.json.gz"),"lock":ref.sha(HERE/"forecast-lock.json"),
         "score_code":ref.sha(HERE/"score.py"),"native_prefix_checks":lock["native_history_checks"]})
    r=panels["50/confirmatory/eligible"];print("PRIMARY",r["n"],r["summary"],r["contrasts"]["exact/final"],flush=True)

if __name__=="__main__":run()
