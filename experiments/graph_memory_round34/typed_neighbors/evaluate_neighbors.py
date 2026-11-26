from channels import D,B,old,f,nm,sha,load,save,R19,np
from fit_neighbors import ARMS
from collections import defaultdict
import sys
KEYS=("FS2048","C2048","R5","MRR")
def paired(cells,a,b):
    g=defaultdict(list)
    for q,r in sorted(cells.items()):g[r["t"]].append(np.array(r["arms"][a])-r["arms"][b])
    d=np.stack([np.sum(g[t],axis=0) for t in sorted(g)]);ns=np.array([len(g[t]) for t in sorted(g)]);arr=np.concatenate(list(g.values()));sm=d.sum(axis=0)/ns.sum()
    out=[];rng=np.random.default_rng(13)
    for _ in range(40):
        ix=rng.integers(len(ns),size=(250,len(ns)));out.append(d[ix].sum(axis=1)/ns[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.vstack(out),[.025,.975],axis=0)
    return {k:dict(delta=float(sm[j]),lo=float(ci[0,j]),hi=float(ci[1,j]),wins=int((arr[:,j]>1e-12).sum()),losses=int((arr[:,j]<-1e-12).sum())) for j,k in enumerate(KEYS)}
def score(stage):
    seal=load(D/(stage+"-seal.json"));p=D/(stage+"-ranks.json.gz");assert sha(p)==seal["ranks"] and sha(D/"models.json")==seal["model"]
    if stage=="test":assert seal["chosen"]==sha(D/"selection.json")
    gold=load(R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else nm.OFF/"gold-spans.json.gz")
    preds=load(p);cells={};hist=load(B/(stage+"-outcomes.json.gz"));hrank=load(B/(stage+"-ranks.json.gz"))
    for src in old.sources(stage):
        for rec in load(src):
            q=rec["q"];r=preds.pop(q);assert r["t"]==rec["t"] and r["ranks"]["frozen"]==hrank[q]["cost_worst_0.03"]
            rr=[nm.pilot.RankedNodeRecord.model_validate(v) for v in rec["rr"]];tr=tuple(nm.pilot.SourceSpan.model_validate(v) for v in gold[q])
            scores={}
            for arm,order in r["ranks"].items():
                assert sorted(order)==list(range(len(rr)));seq=tuple(rr[j] for j in order)
                v=nm.pilot.span_metrics_under_token_budget(seq,tr,2048)
                scores[arm]=[v.full_support,v.coverage,nm.span_metrics_at(seq,tr,5).coverage,nm.span_mrr(seq,tr)]
            ref=hist[q]["arms"]["cost_worst_0.03"];assert scores["frozen"]==[ref[j] for j in (0,3,4,5)]
            cells[q]={"t":rec["t"],"arms":scores}
    assert not preds
    o=D/(stage+"-outcomes.json.gz");save(o,cells)
    means={m:np.mean([r["arms"][m] for r in cells.values()],axis=0).tolist() for m in ARMS}
    summary={"n":len(cells),"t":len({v["t"] for v in cells.values()}),"metrics":KEYS,"means":means,"outcomes":sha(o),"ranks":sha(p),"evaluator":sha(D/"evaluate_neighbors.py")}
    if stage=="dev":
        controls=ARMS[:5];selected=max(controls,key=lambda m:(means[m][0],means[m][1],-controls.index(m)))
        fit=load(D/"train-inputs.json")["identifier"];dev=load(D/"dev-inputs.json")["identifier"]
        good=fit["agree_questions"]>=10 and dev["agree_questions"]>=20 and dev["sham_questions_different"]>=20
        save(D/"selection.json",{"control":selected,"treatment":"agreement","identified":good,"dev":sha(o),"weights":sha(D/"models.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"fit_diag":fit,"dev_diag":dev})
    else:
        c=load(D/"selection.json")["control"];summary["primary_control"]=c
        summary["paired"]={m:paired(cells,"agreement",m) for m in ARMS if m!="agreement"}
        summary["stop_rule_positive"]=summary["paired"][c]["FS2048"]["lo"]>0
    save(D/(stage+"-results.json"),summary);print(stage,[(k,round(v[0]*100,3)) for k,v in means.items()],flush=True)
if __name__=="__main__":score(sys.argv[1])