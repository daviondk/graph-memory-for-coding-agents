"""Transfer score corrections fitted at seed 13 to four new dense orders."""
from losses import *
from study import ProcessPoolExecutor,paired
R21=WORK/"graph_memory_round21/five_seed";SEEDS=(17,29,37,41)
def predict(i):
    rows={r["q"]:r for r in load(PRIVATE/"test.json.gz")}
    prior={r["q"]:r for r in load(REL/f"rep-ranks-{i}.json.gz")}
    chosen=load(ROOT/"selection.json");models=load(ROOT/"models.json")["models"]
    out={}
    for seed in SEEDS:
        key=str(seed);p=R21/f"seed-{seed}";path=p/f"picks-{i}.json.gz";cert=load(p/"forecast-seal.json");lock=next(z for z in cert["receipts"] if z["file"]==path.name)
        assert sha(path)==lock["sha"] and sha(p/"calibration.json")==cert["rank_weights"];cal=load(p/"calibration.json")["rank"]
        for orig in load(path):
            q=orig["q"];row=rows[q];dx=np.array(orig["dense"]);n=len(dx);x=np.array(row["x"])[dx]
            baseline=np.array(row["o"])-f.lin(RANK,f.rank_x(n));s=baseline[dx]+f.lin(cal,f.rank_x(n))
            # Costs, roles and interactions follow the node; only the rank column follows the current ordering.
            x[:,0]=np.log1p(np.arange(1,n+1))
            frozen=dx[np.argsort(-s,kind="stable")].tolist()
            assert frozen==prior[q]["orders"][key]["global_role"]
            selected={}
            for name in [chosen["chosen"]["point"],chosen["policy"]]:
                model=models[name];update=(x-model["center"])/model["scale"]@model["weights"]
                selected[name]=dx[np.argsort(-(s+update),kind="stable")].tolist()
            out.setdefault(q,{})[key]=selected
    fn=ROOT/f"transfer-ranks-{i}.json.gz";save(fn,out);return fn.name,sha(fn)
def evaluate(i):
    base=load(sources("test")[i]);refs=load(nm.OFF/"gold-spans.json.gz");ranks=load(ROOT/f"transfer-ranks-{i}.json.gz");frozen=load(REL/f"rep-outcomes-{i}.json.gz")
    out={}
    for r in base:
        q=r["q"];rr=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];gold=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q])
        arms={}
        for seed,methods in ranks[q].items():
            by_arm={"frozen":frozen[q]["seeds"][seed]["global_role"]}
            for a,ix in methods.items():
                assert sorted(ix)==list(range(len(rr)))
                nodes=tuple(rr[j] for j in ix);vals=[nm.pilot.span_metrics_under_token_budget(nodes,gold,k) for k in (512,1024,2048)]
                by_arm[a]=[vals[2].full_support,*[v.coverage for v in vals],nm.span_metrics_at(nodes,gold,5).coverage,nm.span_mrr(nodes,gold)]
            arms[seed]=by_arm
        out[q]={"t":r["t"],"seeds":arms}
    fn=ROOT/f"transfer-outcomes-{i}.json.gz";save(fn,out);return fn.name,sha(fn)
def main():
    assert sha(PRIVATE/"test.json.gz")==load(ROOT/"test-input.json")["features"]
    with ProcessPoolExecutor(2) as p:forecasts=dict(p.map(predict,range(8)))
    save(ROOT/"transfer-seal.json",{"rank":forecasts,"dev":sha(ROOT/"selection.json"),"protocol":sha(ROOT/"TRANSFER_RU.md"),"code":sha(Path(__file__))})
    with ProcessPoolExecutor(2) as p:parts=dict(p.map(evaluate,range(8)))
    rows={}
    for path,h in parts.items():assert sha(ROOT/path)==h;rows.update(load(ROOT/path))
    assert len(rows)==2000
    for q,r in load(ROOT/"test-outcomes.json.gz").items():rows[q]["seeds"]["13"]=r["arms"]
    selection=load(ROOT/"selection.json");point=selection["chosen"]["point"];primary=selection["policy"]
    summary={}
    for k,seeds in [(str(s),[s]) for s in (13,*SEEDS)]+[("extra4",SEEDS),("all5",(13,*SEEDS))]:
        cells={q:{"t":r["t"],"arms":{a:np.mean([r["seeds"][str(s)][a] for s in seeds],axis=0).tolist() for a in ("frozen",point,primary)}} for q,r in rows.items()}
        tab={a:np.mean([r["arms"][a] for r in cells.values()],axis=0).tolist() for a in ("frozen",point,primary)}
        contrasts={}
        for b in ["frozen",point]:
            by={q:{"t":r["t"],"arms":{"global":r["arms"][b],"candidate":r["arms"][primary]}} for q,r in cells.items()}
            contrasts[b]=paired(by,"candidate")
        summary[k]={"means":tab,"vs":contrasts}
    save(ROOT/"transfer-results.json",{"data":summary,"outcomes":parts,"seal":sha(ROOT/"transfer-seal.json")})
if __name__=="__main__":main()
