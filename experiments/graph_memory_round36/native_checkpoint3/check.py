"""Verify the fixed 6,000 paired outcomes and rederive both bootstrap intervals."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
HOME=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check():
    seeds=[13,17,29];models=["candidate","full_rgcn","wo_chunk_adjacency"]
    metrics=["full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr"]
    p=read(HOME/"plan.json");result=read(HOME/"interim-3.json")
    assert p["protocol"]==sha(HOME/"PROTOCOL_RU.md") and sha(HOME/"epoch-plan.json")=="a0db92075a07376d7d869817646e9c3698d9f1eec664f78dd2bdbc95f8c4944c"
    raw=[]
    for seed in seeds:
        rec=read(HOME/f"audit-{seed}.json");values=HOME/f"outcomes-{seed}.json.gz"
        assert rec["plan"]==sha(HOME/"plan.json") and rec["rows"]==sha(values) and rec["code"]==sha(HOME/"compare.py")
        meta=read(HOME/f"seed-{seed}.json")["checkpoint_audit"]
        assert all(meta["graph"][m]["dev_eval_queries"]==580 and rec["native"][m]["dense_weight"]==meta["dense_parameters"] for m in models[1:])
        assert rec["recomputed"]==6000 and rec["metrics"]==metrics
        raw.append(read(values))
    ids=sorted(raw[0]);assert len(ids)==2000 and all(set(ids)==set(x) for x in raw)
    traj=[raw[0][q][0] for q in ids];assert all(traj==[x[q][0] for q in ids] for x in raw)
    uniq,group=np.unique(np.array(traj),return_inverse=True);assert len(uniq)==1207
    counts=np.bincount(group)
    values=np.array([[r[q][1:] for q in ids] for r in raw]);assert values.shape==(3,2000,3,6) and np.all((values>=0)&(values<=1))
    assert result["completed"] is False and result["gains_both_confirmed"] is None and result["seeds"]==seeds
    def close(a,b):assert np.allclose(a,b,atol=1e-12,rtol=0)
    for j,m in enumerate(models):
        close(values[:,:,j,:].mean((0,1)),[result["means"][m][k] for k in metrics])
    for j,m in enumerate(models[1:],1):
        diff=values[:,:,0,:]-values[:,:,j,:];cluster=np.zeros((len(seeds),1207,6))
        for i in range(len(seeds)):np.add.at(cluster[i],group,diff[i])
        base=cluster.mean(axis=0);r=np.random.default_rng(34091);rseed=np.random.default_rng(34092);direct=[];both=[]
        for _ in range(100):
            selected=r.integers(1207,size=(100,1207))
            seeds_sampled=rseed.integers(len(seeds),size=(100,len(seeds)))
            for draw,ss in zip(selected,seeds_sampled):
                mult=np.bincount(draw,minlength=1207);den=mult@counts
                direct.append(mult@base/den)
                both.append(sum(mult@cluster[s] for s in ss)/(len(seeds)*den))
        bounds=np.quantile(direct,[.025,.975],axis=0);cross=np.quantile(both,[.025,.975],axis=0)
        for k,num in zip(metrics,range(6)):
            orig=result["comparisons"][m][k]
            close(orig["delta"],diff[:,:,num].mean());close(orig["conditional_ci"],bounds[:,num]);close(orig["crossed_ci"],cross[:,num])
            close([orig["per_seed"][str(s)] for s in seeds],diff[:,:,num].mean(axis=1))
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seal",action="store_true");a=parser.parse_args()
    check()
    sources={p.name:sha(p) for p in HOME.iterdir() if p.is_file() and p.name!="manifest.json"}
    dest=HOME/"manifest.json"
    if a.seal and not dest.exists():dest.write_text(json.dumps(sources,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8",newline="\n")
    assert read(dest)==sources
    print("Verified 6,000 paired rows, all six endpoints and two forms of confidence interval.",sha(dest),flush=True)
if __name__=="__main__":main()
