import sys
from pathlib import Path
S=Path(__file__).resolve().parent;D=S.parent;sys.path.insert(0,str(D))
from input_rows import W,R19,R21,PRIVATE,np,pilot,load,sha,write,testparents
from models import order
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget,span_metrics_at,span_mrr
from collections import defaultdict
SEEDS=(17,29,37,41)
ARMS=("dense","factor","alpha_0.75","global_0.03")
KS=("full_support","coverage","recall5","mrr")
def predict():
    model=load(D/"models.json");pbase=load(D/"dev-selection.json");assert pbase["selected"]["control"]==ARMS[-1] and pbase["selected"]["constant"]==ARMS[-2]
    assert load(D/"test-inputs.json")["file"]==sha(PRIVATE/"test.json.gz")
    numbered={r["q"]:r for r in load(PRIVATE/"test.json.gz")};receipt={}
    for seed in SEEDS:
        h=R21/"five_seed"/f"seed-{seed}";cal=h/"calibration.json"
        model["rank"]=load(cal)["rank"];seal=load(h/"forecast-seal.json");assert seal["rank_weights"]==sha(cal)
        select=R21/"five_seed/dev580"/f"seed-{seed}/selection.json"
        assert load(select)["same_choice"] is True
        out=[]
        for i,entry in enumerate(seal["receipts"]):
            path=h/entry["file"];assert sha(path)==entry["sha"]
            for saved in load(path):
                r=numbered[saved["q"]];assert saved["t"]==r["t"]
                dense=np.asarray(saved["dense"]);p=np.asarray(r["p"])[dense]
                inp={"p":p,"x":np.zeros(8)};ranks={a:dense[order(inp,model,a)].tolist() for a in ARMS}
                assert ranks["factor"]==saved["factor"] and ranks["dense"]==saved["dense"]
                out.append(dict(q=r["q"],t=r["t"],rank=ranks))
        assert len(out)==len({r["q"] for r in out})==2000
        path=S/f"seed-{seed}-picks.json.gz";write(path,out)
        receipt[seed]={"ranks":sha(path),"calibration":sha(cal),"dense":sha(h/"forecast-seal.json"),"checkpoint_selection":sha(select)}
        print("sealed",seed,flush=True)
    write(S/"seal.json",{"seeds":receipt,"protocol":sha(S/"PROTOCOL_RU.md"),"code":sha(S/"transfer.py"),"seed13_model":sha(D/"models.json"),"seed13_selection":sha(D/"dev-selection.json"),"seed13_discovery":sha(D/"test-metrics.json")})
def boot(cells,seeds,contrast):
    a,b=contrast;gs=defaultdict(list)
    for q in sorted(cells[seeds[0]][a]):
        ts=[];dv=[]
        for z in seeds:
            x=cells[z][a][q];y=cells[z][b][q];assert x[0]==y[0];ts.append(x[0]);dv.append(np.asarray(x[1:])-np.asarray(y[1:]))
        assert len(set(ts))==1;gs[ts[0]].append(np.mean(dv,axis=0))
    sums=np.asarray([np.sum(gs[t],axis=0) for t in sorted(gs)]);n=np.asarray([len(gs[t]) for t in sorted(gs)])
    bs=[];rng=np.random.default_rng(13)
    for _ in range(40):
        ix=rng.integers(len(n),size=(250,len(n)));bs.append(sums[ix].sum(axis=1)/n[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(bs),[.025,.975],axis=0);d=sums.sum(axis=0)/n.sum()
    return {k:[float(d[j]),*ci[:,j].tolist()] for j,k in enumerate(KS)}
def score():
    seal=load(S/"seal.json");assert seal["code"]==sha(S/"transfer.py")
    gold=load(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz");cells={}
    masks={}
    for z in SEEDS:
        p=S/f"seed-{z}-picks.json.gz";assert sha(p)==seal["seeds"][str(z)]["ranks"]
        masks[z]={r["q"]:r for r in load(p)}
        cells[z]={a:{} for a in ARMS}
    for src in testparents():
        for u in load(src):
            q=u["q"];nodes=[pilot.RankedNodeRecord.model_validate(y) for y in u["rr"]]
            tr=tuple(pilot.SourceSpan.model_validate(y) for y in gold[q])
            for z in SEEDS:
                m=masks[z].pop(q);assert m["t"]==u["t"]
                for a in ARMS:
                    seq=tuple(nodes[j] for j in m["rank"][a]);v=span_metrics_under_token_budget(seq,tr,2048)
                    cells[z][a][q]=[m["t"],v.full_support,v.coverage,span_metrics_at(seq,tr,5).coverage,span_mrr(seq,tr)]
    assert all(not v for v in masks.values())
    for z in SEEDS:
        hist=load(R21/f"five_seed/seed-{z}/metrics.json.gz")
        for a in ("dense","factor"):
            for q,x in cells[z][a].items():
                y=hist[a][q];assert x[0]==y["t"] and list(x[1:])==[y[k] for k in ("full_support_2048","coverage_2048","recall_5","mrr")]
    x0=load(D/"test-outcomes.json.gz");cells[13]={a:x0[a] for a in ARMS}
    path=S/"outcomes.json.gz";write(path,cells)
    summary={z:{a:dict(zip(KS,np.mean([r[1:] for r in rs.values()],axis=0).tolist())) for a,rs in ss.items()} for z,ss in cells.items()}
    results={"per_seed":summary,"intervals":{},"means":{},"seal":sha(S/"seal.json"),"outcomes":sha(path),"n":2000,"t":1207}
    for label,seeds in [("transfer",SEEDS),("all",(13,*SEEDS))]:
        results["intervals"][label]={" vs ".join(pair):boot(cells,seeds,pair) for pair in [(ARMS[-1],"factor"),(ARMS[-1],ARMS[-2]),(ARMS[-2],"factor")]}
        results["means"][label]={a:{k:float(np.mean([summary[z][a][k] for z in seeds])) for k in KS} for a in ARMS}
    write(S/"results.json",results)
if __name__=="__main__":{"predict":predict,"score":score}[sys.argv[1]]()