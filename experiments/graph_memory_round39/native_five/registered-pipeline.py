"""Resumable CPU-only follow-up of canonical and development-metric-matched official pairs."""
from pathlib import Path
import gzip,hashlib,json,os,sys,time,importlib.util
for env in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[env]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
D=Path(__file__).resolve().parent;W=D.parents[1];ORIG=W/"graph_memory_round36/native_three_seeds";N=W/"graph_memory_round34/native_comparison"
S=W/"graph_memory_round34/dev_metric";T=W/"graph_memory_round35/calibration_transfer";OFF=W/"graph_memory_round22/native_multiseed/official580"
SEEDS=[13,17,29,37,41];FORWARD=[37,41];ARMS=["full_rgcn","wo_chunk_adjacency"]
MODELS=["R35_oof_3894","R33_cost_worst",*ARMS];METRICS=["full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr"]
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode();tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b);tmp.replace(p)
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def verify_plan():
    exp=read(D/"plan.json");assert sha(D/"plan.json")=="b6774b1837b126d8e17425856daf80b9149a81e39c29c216f94d295539303f34"
    assert exp["files"]=={"protocol":sha(D/"PROTOCOL_RU.md"),"three":sha(ORIG/"manifest.json"),"native":sha(N/"plan.json"),"sensitivity":sha(S/"plan.json"),"r35":sha(T/"manifest.json")}
def rows_path(mode,s):return D/f"{mode}-{s}.json.gz"
def checked_seed(s):
    audit=read(N/f"audit-{s}.json");old=N/f"outcomes-{s}.json.gz";assert audit["rows"]==sha(old) and audit["plan"]==sha(N/"plan.json") and audit["recomputed"]==6000
    if s in [13,17,29]:
        fp=ORIG/f"four-arms-{s}.json.gz";assert sha(fp)==read(ORIG/"manifest.json")[fp.name]
        data=read(fp);vals=read(old);assert set(data)==set(vals) and all([x[0],*x[2:]]==vals[q] for q,x in data.items())
        return data,{"previous":sha(fp),"native":sha(old),"pair_audit":sha(N/f"audit-{s}.json")}
    import numpy as np
    m=module("r36_four_methods_native",ORIG/"measure.py");nm=m.nm
    known=read(old);pub=read(T/"outcomes.json.gz");gold=read(nm.OFF/"gold-spans.json.gz");out={}
    assert sha(T/"outcomes.json.gz")==read(T/"measure-seal.json")["outcomes"]
    orderseal=read(T/"forecast-seal.json")["orders"];links={}
    for i,src in enumerate(m.sources("test")):
        rp=T/f"orders-{i}.json.gz";assert sha(rp)==orderseal[rp.name];sorder=read(rp);links[rp.name]=sha(rp)
        for row in read(src):
            q=row["q"];t=row["t"];r=known[q];assert pub[q]["t"]==r[0]==t
            nodes=tuple(nm.pilot.RankedNodeRecord.model_validate(z) for z in row["rr"]);g=tuple(nm.pilot.SourceSpan.model_validate(z) for z in gold[q]);idx=sorder[q][str(s)]["oof_3894"]
            assert sorted(idx)==list(range(len(nodes)));ranked=tuple(nodes[k] for k in idx)
            z=[nm.pilot.span_metrics_under_token_budget(ranked,g,b) for b in (512,1024,2048)]
            score=[float(z[-1].full_support),*[float(x.coverage) for x in z],float(nm.span_metrics_at(ranked,g,5).coverage),float(nm.span_mrr(ranked,g))]
            orig=pub[q]["seeds"][str(s)]
            for key,got in [("oof_3894",score),("original_R33",r[1])]:
                want=orig[key];assert np.allclose([got[0],got[5],got[3]],[want[0],want[3],want[4]],atol=1e-12,rtol=0)
            out[q]=[t,score,*r[1:]]
    assert out.keys()==known.keys() and len(out)==2000
    return out,{"native":sha(old),"pair_audit":sha(N/f"audit-{s}.json"),"order_shards":links,"all_r35":sha(T/"outcomes.json.gz")}
def make_rows(mode,s):
    dest=rows_path(mode,s);receipt=D/f"{mode}-receipt-{s}.json"
    if receipt.exists():
        assert read(receipt)["rows"]==sha(dest);return
    if mode=="canonical":out,proof=checked_seed(s)
    else:
        cert=read(S/"manifest.json");proof={"dev_epoch_manifest":sha(S/"manifest.json"),"all_dev":sha(S/"all-dev-seal.json"),"reruns":{}}
        base=read(rows_path("canonical",s));scores={}
        for arm in ARMS:
            f=S/f"test-results-{s}-{arm}.json.gz";g=S/f"dev-selection-{s}-{arm}.json";assert cert[f.name]==sha(f) and cert[g.name]==sha(g)
            ds=read(g);proof["reruns"][arm]={"epoch":ds["selected"]["epoch"],"same_original_weight":ds["same_recall_winner_weights"],"dev":sha(g),"test":sha(f)}
            scores[arm]=read(f);assert set(scores[arm])==set(base)
        out={}
        for q,x in base.items():
            rows=[scores[m][q] for m in ARMS];assert all(r[0]==x[0] for r in rows)
            out[q]=[x[0],*x[1:3],*[r[1] for r in rows]]
    put(dest,out);put(receipt,{"plan":sha(D/"plan.json"),"program":sha(D/"pipeline.py"),"seed":s,"rows":sha(dest),"proof":proof})
def aggregate(mode,seeds):
    import numpy as np
    stats=module("r36_matched_intervals",ORIG/"analyze.py")
    by=[read(rows_path(mode,s)) for s in seeds];qs=sorted(by[0]);ts=[by[0][q][0] for q in qs]
    assert len(qs)==2000 and all(set(x)==set(qs) and [x[q][0] for q in qs]==ts for x in by)
    parents,ids=np.unique(ts,return_inverse=True);assert len(parents)==1207
    array=np.array([[x[q][1:] for q in qs] for x in by]);assert array.shape==(len(seeds),2000,4,6)
    compared={}
    for a,b in [(0,2),(0,3),(1,2),(1,3),(0,1)]:
        compared[MODELS[a]+"/"+MODELS[b]]=stats.estimate(array[:,:,a,:]-array[:,:,b,:],ids,METRICS,seeds)
    z=[compared[MODELS[0]+"/"+m][METRICS[0]] for m in ARMS]
    return {"seeds":seeds,"test_questions":2000,"test_trajectories":1207,"means":{m:array[:,:,j,:].mean((0,1)).tolist() for j,m in enumerate(MODELS)},"per_seed_means":{str(s):{m:array[i,:,j,:].mean(0).tolist() for j,m in enumerate(MODELS)} for i,s in enumerate(seeds)},"comparisons":compared,"both_positive_points":all(x["delta"]>0 for x in z),"both_lower_bounds_positive_in_both_intervals":all(x[k][0]>0 for x in z for k in ("conditional_ci","crossed_ci"))}
def finish(mode):
    target=D/f"{mode}-complete.json"
    if target.exists():
        module("r37_native_report",D/"report.py").publish(mode);return
    full=aggregate(mode,SEEDS);forward=aggregate(mode,FORWARD)
    put(target,{"five":full,"forward":forward,"plan":sha(D/"plan.json"),"rows":{str(s):sha(rows_path(mode,s)) for s in SEEDS}})
    module("r37_native_report",D/"report.py").publish(mode)
    print("Completed all five and forward comparison",mode,sha(target),flush=True)
def once():
    verify_plan()
    for s in SEEDS:
        if not (N/f"audit-{s}.json").exists():continue
        prior=(D/f"canonical-receipt-{s}.json").exists();make_rows("canonical",s)
        if s in FORWARD and not (D/f"canonical-just-{s}.json").exists():
            put(D/f"canonical-just-{s}.json",aggregate("canonical",[s]));print("New paired input",s,flush=True)
    if all((D/f"canonical-receipt-{s}.json").exists() for s in SEEDS):
        finish("canonical")
        if (S/"manifest.json").exists():
            for s in SEEDS:make_rows("metric-matched",s)
            finish("metric-matched")
            canonical=read(D/"canonical-complete.json");match=read(D/"metric-matched-complete.json")
            eq={f"{s}/{a}":read(D/f"metric-matched-receipt-{s}.json")["proof"]["reruns"][a]["same_original_weight"] for s in SEEDS for a in ARMS}
            if not (D/"final.json").exists():put(D/"final.json",{"positive_in_both_protocols":all(r["five"]["both_lower_bounds_positive_in_both_intervals"] for r in (canonical,match)),"same_original_weights":eq,"all_replays_reproduced":all(eq.values()),"canonical":sha(D/"canonical-complete.json"),"metric_matched":sha(D/"metric-matched-complete.json")})
    if (D/"final.json").exists():
        import subprocess
        subprocess.run([sys.executable,"-B",str(D/"verify.py")],check=True)
    return (D/"final.json").exists()
if __name__=="__main__":
    while True:
        done=once()
        if done or "--watch" not in sys.argv:break
        time.sleep(20)
