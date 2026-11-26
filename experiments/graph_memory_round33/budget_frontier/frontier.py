"""Compare budget-dependent routing and a single reusable prefix-preserving order."""
from pathlib import Path
import sys,hashlib
HERE=Path(__file__).resolve().parent;BUDGET=HERE.parent/"budget_loss";sys.path.insert(0,str(BUDGET))
from data import PRIVATE,REL,nm,R19,np,load,save,sha,sources
from study import paired
from itertools import combinations
B=(256,512,1024,2048,4096)
A=("a0","a1","a2","a3","a4")
MODES=(*A,"prefix256","prefix512")
def prefix(order,cost,b):
    used=0
    for i,j in enumerate(order):
        used+=cost[j]
        if used>b:return order[:i]
    return order

def ranked(stage):
    if stage=="test":assert (HERE/"selection.json").exists()
    parent=load(BUDGET/"selection.json");name=parent["policy"];m=load(BUDGET/"models.json")["models"][name]
    rows=load(PRIVATE/(stage+".json.gz"));assert sha(PRIVATE/(stage+".json.gz"))==load(BUDGET/(stage+"-input.json"))["features"]
    reference=load(BUDGET/(stage+"-ranks.json.gz"));out={}
    for row in rows:
        q=row["q"];o=np.asarray(row["o"]);x=np.asarray(row["x"])
        update=(x-m["center"])/m["scale"]@m["weights"]
        ranks={a:np.argsort(-(o+i*update/4),kind="stable").tolist() for i,a in enumerate(A)}
        assert ranks["a0"]==reference[q]["frozen"] and ranks["a4"]==reference[q][name]
        for limit in (256,512):
            n=min(len(ranks["a0"]),len(prefix(ranks["a0"],row["c"],limit))+1)
            head=ranks["a0"][:n];hs=set(head);order=head+[j for j in ranks["a4"] if j not in hs]
            assert len(set(order))==len(order)==len(o)
            for b in B:
                if b<=limit:assert prefix(order,row["c"],b)==prefix(ranks["a0"],row["c"],b)
            ranks["prefix"+str(limit)]=order
        out[q]=ranks
    rp=HERE/(stage+"-ranks.json.gz");save(rp,out);save(HERE/(stage+"-seal.json"),{"rank":sha(rp),"policy":sha(BUDGET/"selection.json"),"parent":sha(BUDGET/(stage+"-seal.json")),"protocol":sha(HERE/"PROTOCOL_RU.md"),"script":sha(Path(__file__)),"selection":sha(HERE/"selection.json") if stage=="test" else None})
    return out
def project(stage,ranks):
    assert sha(HERE/(stage+"-ranks.json.gz"))==load(HERE/(stage+"-seal.json"))["rank"]
    refs=load(R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else nm.OFF/"gold-spans.json.gz")
    outcomes={}
    for path in sources(stage):
        for r in load(path):
            q=r["q"];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];g=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q])
            methods={}
            for m,ix in ranks[q].items():
                ns=tuple(nodes[j] for j in ix);vals=[nm.pilot.span_metrics_under_token_budget(ns,g,b) for b in B]
                methods[m]={"c":[v.coverage for v in vals],"fs":[v.full_support for v in vals],"mrr":nm.span_mrr(ns,g)}
            outcomes[q]={"t":r["t"],"methods":methods}
    assert outcomes.keys()==ranks.keys();save(HERE/(stage+"-outcomes.json.gz"),outcomes)
    return outcomes

def choose(rows):
    ids=sorted({r["t"] for r in rows.values()},key=lambda t:hashlib.sha256(("frontier-v1/"+t).encode()).digest())
    assert len(ids)==352;cal=set(ids[:len(ids)//2]);hold=set(ids[len(ids)//2:]);assert not cal&hold
    scores={m:np.mean([r["methods"][m]["c"] for r in rows.values() if r["t"] in cal],axis=0) for m in MODES}
    best_single=max(A,key=lambda m:round(float(scores[m].mean()),12));best_prefix=max(("prefix256","prefix512"),key=lambda m:round(float(scores[m].mean()),12))
    binary=[max(("a0","a4"),key=lambda m:round(float(scores[m][i]),12)) for i in range(5)]
    free=[max(A,key=lambda m:round(float(scores[m][i]),12)) for i in range(5)]
    schedules={}
    for i,j in combinations(range(5),2):
        # At a quarter-grid midpoint, choose the lower alpha.
        schedules[i,j]=[min(range(5),key=lambda k:abs(k-4*max(0,min(1,(b-i)/(j-i))))) for b in range(5)]
    best=max(schedules,key=lambda key:round(float(np.mean([scores[A[k]][b] for b,k in enumerate(schedules[key])])),12))
    policies={"frozen":["a0"]*5,"cost":["a4"]*5,"best_single":[best_single]*5,"binary_by_budget":binary,"free_by_budget":free,"smooth":[A[k] for k in schedules[best]],"fixed_switch":["a0","a0","a4","a4","a4"],"single_prefix":[best_prefix]*5}
    save(HERE/"selection.json",{"cal_t":sorted(cal),"hold_t":sorted(hold),"cal_questions":sum(r["t"] in cal for r in rows.values()),"dev":sha(HERE/"dev-outcomes.json.gz"),"policies":policies,"smooth_bounds":[B[i] for i in best],"cal_scores":{m:v.tolist() for m,v in scores.items()}})
    return policies,cal,hold

def measure(rows,ranks,source_features,policies,panel):
    output={};nonnested={};unique={}
    for q,r in rows.items():
        if panel is not None and r["t"] not in panel:continue
        cost=source_features[q];methods=r["methods"];arms={};checked={}
        for p,schedule in policies.items():
            cov=[methods[m]["c"][i] for i,m in enumerate(schedule)]
            arms[p]=[sum(cov)/5,*cov,methods[schedule[3]]["fs"][3],methods[schedule[1]]["mrr"],methods[schedule[3]]["mrr"]]
            selected=[set(prefix(ranks[q][m],cost,b)) for m,b in zip(schedule,B)]
            violations=sum(not l.issubset(h) for l,h in zip(selected,selected[1:]));checked[p]=violations
            nonnested[p]=nonnested.get(p,0)+violations;unique[p]=unique.get(p,0)+len({tuple(ranks[q][m]) for m in schedule})
            if len(set(schedule))==1:assert not violations
        output[q]={"t":r["t"],"arms":arms,"non_nested":checked}
    results={"n":len(output),"t":len({r["t"] for r in output.values()}),"means":{p:np.mean([r["arms"][p] for r in output.values()],axis=0).tolist() for p in policies},"vs":{},
             "non_nested_transitions":nonnested,"mean_unique_rankings":{k:n/len(output) for k,n in unique.items()}}
    for a,b in [("smooth","best_single"),("smooth","binary_by_budget"),("binary_by_budget","best_single"),("fixed_switch","best_single"),("single_prefix","best_single"),("single_prefix","frozen"),("single_prefix","cost"),("smooth","cost"),("free_by_budget","binary_by_budget")]:
        if all(r["arms"][a]==r["arms"][b] for r in output.values()):
            zero=[0]*len(next(iter(output.values()))["arms"][a]);res={"delta_pp":zero,"ci95_pp":[zero,zero]}
        else:
            cells={q:{"t":r["t"],"arms":{"global":r["arms"][b],"candidate":r["arms"][a]}} for q,r in output.items()};v=paired(cells,"candidate");res={k:v[k] for k in ("delta_pp","ci95_pp")}
        results["vs"][a+" vs "+b]=res
    return output,results
def main():
    summaries={}
    for stage in ("dev","test"):
        ranks=ranked(stage);outcomes=project(stage,ranks);features={r["q"]:r["c"] for r in load(PRIVATE/(stage+".json.gz"))}
        if stage=="dev":policies,cal,hold=choose(outcomes);panels={"dev_cal":cal,"dev_hold":hold}
        else:policies=load(HERE/"selection.json")["policies"];panels={"test":None}
        for label,group in panels.items():
            out,summary=measure(outcomes,ranks,features,policies,group);save(HERE/(label+"-policy-rows.json.gz"),out)
            summaries[label]=summary;print(label,{k:round(v[0],5) for k,v in summary["means"].items()},flush=True)
    save(HERE/"results.json",{"metrics":["MeanCoverage","C256","C512","C1024","C2048","C4096","FS2048","MRR_order_at_512","MRR_order_at_2048"],"panels":summaries,"selection":sha(HERE/"selection.json"),"test":sha(HERE/"test-outcomes.json.gz")})
if __name__=="__main__":main()
