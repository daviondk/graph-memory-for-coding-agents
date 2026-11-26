"""Recompute the candidate and both native comparators on identical ordered PU records and gold spans."""
from collections import defaultdict
from pathlib import Path
import gzip,hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent;WORK=HERE.parents[1]
R33=WORK/"graph_memory_round33/budget_loss"
OFF=WORK/"graph_memory_round22/native_multiseed/official580"
DENSE=WORK/"graph_memory_round21/five_seed"
SEEDS=[13,17,29,37,41];ARMS=["full_rgcn","wo_chunk_adjacency"]
METRICS=["full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr"]
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode()
    tmp=p.with_suffix(p.suffix+".partial")
    tmp.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b);tmp.replace(p)
def checked():
    p=get(HERE/"plan.json");sel=get(R33/"selection.json")
    assert sha(HERE/"PROTOCOL_RU.md")==p["protocol"] and sha(R33/"manifest.json")==p["candidate_manifest"]
    assert sha(R33/"selection.json")==p["selection"] and sel["policy"]==p["policy"] and sha(OFF/"plan.json")==p["baseline_plan"]
    for f,h in get(R33/"manifest.json").items():assert sha(R33/f)==h
    return p
def collect(seed):
    p=checked();policy=p["policy"]
    if (HERE/f"audit-{seed}.json").exists():
        prior=get(HERE/f"audit-{seed}.json")
        assert prior["plan"]==sha(HERE/"plan.json") and prior["rows"]==sha(HERE/f"outcomes-{seed}.json.gz")
        return
    sys.path.insert(0,str(R33));from data import nm,sources
    gold_file=nm.OFF/"gold-spans.json.gz";assert sha(gold_file)==p["gold"]
    truth=get(gold_file)
    selection=DENSE/f"dev580/seed-{seed}/selection.json";weights=get(selection);weight=weights["weight_580"]
    link=get(DENSE/f"dev580/seed-{seed}/test-link.json");assert link["weight"]==weight==weights["weight_500"]
    info={};native_ranks={};native_scores={}
    for m in ARMS:
        home=OFF/f"seed-{seed}"/m;se=get(home/"forecast-seal.json");fit=get(home/"fit.json");res=get(home/"results.json")
        assert se["ft"]==fit["weight"]==weight and se["plan"]==p["baseline_plan"] and res["forecast"]==sha(home/"forecast-seal.json")
        assert res["metrics"]==sha(home/"metrics.json.gz")
        info[m]={"fit":sha(home/"fit.json"),"predictions":res["forecast"],"scores":res["metrics"],"checkpoint":se["checkpoint"],"dense_weight":weight}
        native_scores[m]=get(home/"metrics.json.gz")["graph"];native_ranks[m]={}
        for j,r in enumerate(se["receipts"]):
            assert sha(sources("test")[j])==r["source"]
            file=home/r["file"];assert sha(file)==r["sha"]
            for v in get(file):native_ranks[m][v["q"]]=v
    if seed==13:
        cand_rank=get(R33/"test-ranks.json.gz");cand_out=get(R33/"test-outcomes.json.gz")
    pairs={};review={}
    for j,path in enumerate(sources("test")):
        if seed!=13:
            cand_rank={q:x[str(seed)] for q,x in get(R33/f"transfer-ranks-{j}.json.gz").items()}
            cand_out={q:{"t":x["t"],"arms":x["seeds"][str(seed)]} for q,x in get(R33/f"transfer-outcomes-{j}.json.gz").items()}
        for row in get(path):
            q=row["q"];t=row["t"];assert q not in pairs and cand_out[q]["t"]==t
            raw=[nm.pilot.RankedNodeRecord.model_validate(z) for z in row["rr"]];n=len(raw)
            ref=tuple(nm.pilot.SourceSpan.model_validate(z) for z in truth[q]);base={}
            for m in ARMS:
                match=native_ranks[m].pop(q);assert match["t"]==t
                base[m]=match["graph"]
            base["candidate"]=cand_rank[q][policy];scores={}
            for m,ids in base.items():
                assert sorted(ids)==list(range(n))
                ranked=tuple(raw[k] for k in ids)
                b=[nm.pilot.span_metrics_under_token_budget(ranked,ref,x) for x in (512,1024,2048)]
                observed=[float(b[-1].full_support),*[float(x.coverage) for x in b],float(nm.span_metrics_at(ranked,ref,5).coverage),float(nm.span_mrr(ranked,ref))]
                if m=="candidate":expected=cand_out[q]["arms"][policy]
                else:
                    prior=native_scores[m].pop(q);assert prior["t"]==t
                    expected=[prior[k] for k in METRICS]
                assert np.allclose(observed,expected,atol=1e-12,rtol=0),(q,m)
                scores[m]=observed
            pairs[q]=[t,scores["candidate"],scores[ARMS[0]],scores[ARMS[1]]]
    assert len(pairs)==2000 and len({v[0] for v in pairs.values()})==1207 and not any(native_scores.values()) and not any(native_ranks.values())
    put(HERE/f"outcomes-{seed}.json.gz",pairs)
    put(HERE/f"audit-{seed}.json",{"seed":seed,"plan":sha(HERE/"plan.json"),"code":sha(Path(__file__)),"dense_dev":sha(selection),
          "epochs_500_580":[weights["epoch_500"],weights["epoch_580"]],"native":info,"rows":sha(HERE/f"outcomes-{seed}.json.gz"),"recomputed":6000,"metrics":METRICS})
def bootstrap(arr,clusters,seeds):
    # arr: seed × query × metric. Preserve same trajectories and seed mixture in both arms.
    names=sorted(set(clusters));indices={t:i for i,t in enumerate(names)};ns=np.zeros(len(names),int)
    sums=np.zeros((len(seeds),len(names),len(METRICS)))
    for q,t in enumerate(clusters):
        ix=indices[t];ns[ix]+=1;sums[:,ix,:]+=arr[:,q,:]
    avg=sums.mean(0);r=np.random.default_rng(34091);rr=np.random.default_rng(34092)
    grouped=[];crossed=[]
    for _ in range(100):
        ix=r.integers(len(names),size=(100,len(names)));den=ns[ix].sum(axis=1)[:,None]
        grouped.extend(avg[ix].sum(axis=1)/den)
        if len(seeds)>1:
            sw=np.stack([np.bincount(o,minlength=len(seeds)) for o in rr.integers(len(seeds),size=(100,len(seeds)))])/len(seeds)
            z=np.zeros((len(ix),len(METRICS)))
            for j in range(len(seeds)):z+=sums[j][ix].sum(axis=1)*sw[:,j,None]
            crossed.extend(z/den)
    means=arr.mean(axis=(0,1));ci=np.quantile(grouped,[.025,.975],axis=0);ci2=np.quantile(crossed,[.025,.975],axis=0) if crossed else None
    return {m:{"delta":float(means[i]),"conditional_ci":ci[:,i].tolist(),"crossed_ci":ci2[:,i].tolist() if ci2 is not None else None} for i,m in enumerate(METRICS)}
def summary(seeds):
    records=[get(HERE/f"outcomes-{s}.json.gz") for s in seeds];qs=sorted(records[0]);assert all(set(v)==set(qs) for v in records)
    tids=[records[0][q][0] for q in qs];assert all(all(v[q][0]==t for q,t in zip(qs,tids)) for v in records)
    arr=np.array([[v[q][1:] for q in qs] for v in records]);names=["candidate",*ARMS];by={}
    for j,m in enumerate(ARMS,1):
        diff=arr[:,:,0,:]-arr[:,:,j,:];z=bootstrap(diff,tids,seeds)
        for i,k in enumerate(METRICS):z[k]["per_seed"]=dict(zip(seeds,diff[:,:,i].mean(axis=1).tolist()))
        by[m]=z
    return {"seeds":seeds,"completed":seeds==SEEDS,"n":len(qs),"trajectories":len(set(tids)),
        "means":{m:dict(zip(METRICS,arr[:,:,j,:].mean(axis=(0,1)).tolist())) for j,m in enumerate(names)},"comparisons":by,
        "gains_both_confirmed":bool(all(by[m][METRICS[0]]["conditional_ci"][0]>0 for m in ARMS)) if seeds==SEEDS else None}
def update():
    verified=[]
    for seed in SEEDS:
        if not all((OFF/f"seed-{seed}"/m/"results.json").exists() for m in ARMS):break
        collect(seed);verified.append(seed)
        snapshot=HERE/f"interim-{len(verified)}.json"
        if not snapshot.exists():put(snapshot,summary(verified.copy()))
    if verified==SEEDS:
        p=HERE/"results.json"
        if not p.exists():
            res=get(HERE/"interim-5.json");res["heldout_seeds_17_to_41"]=summary(SEEDS[1:]);put(p,res)
    print("Verified paired native seeds",verified,flush=True)
if __name__=="__main__":update()
