from collections import Counter,defaultdict
from statistics import mean
from pathlib import Path
import numpy as np
from controls import *
sys.path.insert(0,str(SRC))
from eval.metrics import _affected_claim_ids,_claim_metric
from eval.ground_truth import load_ground_truth_index
def main(panel):
    for p in ("controlled","adapted"):
        assert sha256((D/(p+"-forecasts.json.gz")).read_bytes()).hexdigest()==get(D/(p+"-seal.json"))["forecast_sha"]
    root=SRC/"data"/("controlled_benchmark" if panel=="controlled" else "adapted_lmev2_subset")
    registry={r["task_id"]:r for r in readl(root/"registry.jsonl")}
    pred=get(D/(panel+"-forecasts.json.gz"));pred.sort(key=lambda r:r["task"])
    nroot=P/"native"/panel
    author={r["task_id"]:r for domain in sorted({r["domain"] for r in pred}) for r in get(nroot/(domain+"-metrics.json"))["cases"]}
    native_oracle={r["task_id"]:r["oracle_pass"] for r in readl(nroot/"oracle/oracle_results.jsonl")};assert len(author)==len(pred)==len(native_oracle)
    golds={};items=[];sg=Counter();agg_names=("tp","fp","fn","source_removed","source_total","derived_removed","derived_total","benign_retained","benign_total")
    for f in pred:
        task=f["task"];domain=f["domain"];reg=registry[task];path=root/domain/"ground_truth.jsonl"
        if domain not in golds:golds[domain]=load_ground_truth_index(path)
        raw=golds[domain][task]
        meta=dict(domain=domain,task_id=task,fault_types=reg["fault_types"])
        true=set(_affected_claim_ids(raw,meta,None,path));native=author[task]["affected_claim_invalidation"]
        assert true==set(native["false_negative_ids"]) and native["tp"]==native["fp"]==0
        g=raw["memory_ground_truth"];src=set(g["source_faulty_memories"]);derived=set(g["derived_faulty_memories"]);ben=set(g["benign_active_memory_ids"]);input_fault=set(f["diagnosis"])
        sg["disclosed_exact_source_cases"]+=src==input_fault;sg["disclosed_source_count"]+=len(src&input_fault)
        sg["disclosed_extra_count"]+=len(input_fault-src);sg["disclosed_derived_count"]+=len(input_fault&derived)
        sg["source_count"]+=len(src);sg["derived_count"]+=len(derived);sg["benign_count"]+=len(ben);sg["claim_count"]+=len(true);sg["cases_with_affected_claim"]+=bool(true);sg["cases_with_derived"]+=bool(derived)
        ar={}
        for k,x in f["policies"].items():
            z=set(x["claims"]);m=set(x["mem"]);o=_claim_metric(sorted(true),sorted(z))
            ar[k]=dict(tp=o["tp"],fp=o["fp"],fn=o["fn"],source_removed=len(src&m),source_total=len(src),derived_removed=len(derived&m),derived_total=len(derived),benign_retained=len(ben-m),benign_total=len(ben))
        items.append(dict(task=task,domain=domain,oracle=native_oracle[task],gold_claims=sorted(true),arms=ar))
    methods=list(items[0]["arms"]);ag={};draws=np.random.default_rng(29029).integers(0,len(items),(10000,len(items)))
    def ratio(x,y):
        return np.divide(x,y,out=np.zeros_like(x,dtype=float),where=y!=0)
    def micro(a):return ratio(2*a[...,0],2*a[...,0]+a[...,1]+a[...,2])
    bs={}
    for k in methods:
        mat=np.array([[v["arms"][k][n] for n in agg_names] for v in items],dtype=int)
        sums=mat.sum(0);sample=mat[draws].sum(axis=1);bootstrap=micro(sample);bs[k]=bootstrap
        ag[k]=dict(zip(agg_names,map(int,sums)));ag[k]["f1"]=float(micro(sums));ag[k]["ci"]=np.quantile(bootstrap,[.025,.975]).tolist()
    pairs={}
    for a,b in [("rederive","reach_any"),("direct","rederive"),("direct","reach_any"),("rederive","source")]:
        dv=bs[a]-bs[b];pairs[a+"__"+b]=dict(delta=ag[a]["f1"]-ag[b]["f1"],paired_ci=np.quantile(dv,[.025,.975]).tolist())
    rep=dict(n=len(pred),domains=Counter(r["domain"] for r in pred),native_success=sum(native_oracle.values()),diagnosis=sg,arms=ag,contrasts=pairs,per_case_sha=save(D/(panel+"-per-case.json.gz"),items))
    save(D/(panel+"-results.json"),rep)
    print(panel,sg,{k:round(a["f1"],4) for k,a in ag.items()},pairs)
if __name__=="__main__":main(sys.argv[1])

