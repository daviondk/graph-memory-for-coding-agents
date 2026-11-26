"""Aggregate paired time measurements and cluster uncertainty without rerunning the models."""
from pathlib import Path
from collections import defaultdict
import hashlib,gzip,json,numpy as np
D=Path(__file__).resolve().parent
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(a):
    v=np.asarray(a);return {"p50":float(np.median(v)),"p95":float(np.quantile(v,.95)),"mean":float(np.mean(v)),"min":float(v.min()),"max":float(v.max())}
def main():
    times=get(D/"times.json.gz");ss=get(D/"setup.json.gz");check=get(D/"replay.json.gz")
    mlist=("dense","cost","full_rgcn","wo_chunk_adjacency");summary={}; qids=sorted(check)
    assert len(times)==3840 and len(qids)==96
    for md,R in (("warm",8),("embeddings",2)):
        arms=defaultdict(list)
        for t,q,m,rep,order,a,ns in times:
            if m==md:arms[q,a].append(ns/1e6)
        assert all(len(arms[q,a])==R for q in qids for a in mlist)
        matrix=np.array([[np.median(arms[q,a]) for a in mlist] for q in qids]);by=defaultdict(list)
        for i,q in enumerate(qids):by[check[q]["t"]].append(i)
        groups=[by[t] for t in sorted(by)];sizes=np.array(list(map(len,groups)));sums=np.stack([matrix[j].sum(0) for j in groups])
        rng=np.random.default_rng(13);mb=[]
        for _ in range(100):
            sample=rng.integers(len(groups),size=(100,len(groups)));mb.extend(sums[sample].sum(1)/sizes[sample].sum(1)[:,None])
        mb=np.array(mb);mean=matrix.mean(0);contrasts={}
        for i,j in ((2,1),(3,1),(1,0)):
            contrasts[mlist[i]+" over "+mlist[j]]={"ratio":float(mean[i]/mean[j]),"ratio_ci95":np.quantile(mb[:,i]/mb[:,j],[.025,.975]).tolist(),
                "delta_ms":float(mean[i]-mean[j]),"delta_ci95_ms":np.quantile(mb[:,i]-mb[:,j],[.025,.975]).tolist()}
        summary[md]={"question_medians_ms":{a:stats(matrix[:,i]) for i,a in enumerate(mlist)},"pooled_ms":{a:stats([t for q in qids for t in arms[q,a]]) for a in mlist},"paired":contrasts}
    ts=ss["histories"];qs=ss["queries"];setup={"histories":{k:stats([v[k] for v in ts.values()]) for k in next(iter(ts.values()))},
        "cosine_ns":stats([v["cosine_ns"] for v in qs.values()]),"native":{a:{k:stats([v["native"][a][k] for v in qs.values()]) for k in next(iter(qs.values()))["native"][a]} for a in mlist[2:]}}
    replay={m:{k:sum(v["arms"][m][k] for v in check.values()) for k in ("same_order","same_prefix","fs","reference_fs","n_diff_ranks")} for m in mlist}
    for m in mlist:replay[m]["equal_fs_states"]=sum(v["arms"][m]["fs"]==v["arms"][m]["reference_fs"] for v in check.values())
    memory={}
    if all((D/f"memory-{m}-{i}.json").exists() for m in mlist for i in (1,2)):
        for m in mlist:
            items=[get(D/f"memory-{m}-{i}.json") for i in (1,2)]; assert all(v["sha"]=={q:check[q]["arms"][m]["order_sha"] for q,t in v["panel"]} for v in items)
            memory[m]={}
            for field in ("WorkingSetSize","PeakWorkingSetSize","PrivateUsage"):
                memory[m][field]={k:[it["snapshots"][k][field] for it in items] for k in items[0]["snapshots"]}
    res={"queries":96,"histories":len(ts),"summary":summary,"setup":setup,"replay":replay,"private_processes":memory,"timings_sha":sha(D/"times.json.gz")}
    (D/"summary.json").write_text(json.dumps(res,sort_keys=True,indent=2)+"\n",encoding="utf8")
    for m,r in summary.items():print(m,{a:round(v["p50"],3) for a,v in r["question_medians_ms"].items()},r["paired"])
if __name__=="__main__":main()
