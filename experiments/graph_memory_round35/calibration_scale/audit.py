"""Independent prefix/outcome audit via atomic gold coordinates and manual log-budget trapezoid."""
import sys
from prepare_scale import *
from collections import defaultdict
BS=np.array([256,512,1024,2048,4096,8192])
def analyze(stage):
    feats={r["q"]:r for r in load(b.PRIVATE/(stage+".json.gz"))};atoms=load(ARCH/(stage+"-atoms.json.gz"))
    assert sha(ARCH/(stage+"-atoms.json.gz"))==load(ARCH/(stage+"-geometry.json"))["atoms"]
    rr=load(D/(stage+"-orders.json.gz"));out=load(D/(stage+"-outcomes.json.gz"));means={a:[] for a in next(iter(rr.values()))};n=0
    for q,row in out.items():
        a=atoms[q];length=np.array([right-left for field,left,right,g in a]);cs=np.asarray(feats[q]["c"]);cache={}
        for name,order in rr[q].items():
            key=tuple(order)
            if key not in cache:
                order=np.asarray(order);rank=np.argsort(order);first=np.array([min(rank[i] for i in group) for *_,group in a]);spent=np.cumsum(cs[order])[first]
                support=np.array([int(spent.max()<=cap) for cap in BS]);coverage=np.array([length[spent<=cap].sum()/length.sum() for cap in BS])
                # Equal log2 spacing => normalized trapezoidal weights on grid intervals.
                auc=lambda v:float((v[0]/2+v[-1]/2+v[1:-1].sum())/5)
                cache[key]=[support[3],auc(coverage),auc(support),1/(1+first.min()),coverage[3]];n+=1
            assert np.allclose(cache[key],row["arms"][name],rtol=0,atol=1e-12),(q,name,cache[key],row["arms"][name]);means[name].append(cache[key])
    r=load(D/(stage+"-results.json"));assert all(np.allclose(np.mean(z,axis=0),r["means"][a],rtol=0,atol=1e-12) for a,z in means.items())
    return dict(questions=len(out),methods=len(means),unique_orders_checked=n,metric_checks=n*5)
def main():
    inv=load(D/"train-inventory.json");f=load(D/"fold-models.json");records=inv["records"]
    for k,entry in f["folds"].items():
        k=int(k);training={r["t"] for r in records.values() if r["prior"] and r["fold"]!=k};held={r["t"] for r in records.values() if r["fold"]==k}
        assert not training&held and len(training)==entry["graph_t"] and entry["graph_trajectory_sha"]==digest("\n".join(sorted(training)))
        rank={q for q,r in records.items() if r["rank_fit"] and r["fold"]!=k};assert len(rank)==entry["rank_questions"] and entry["rank_query_sha"]==digest("\n".join(sorted(rank)))
    summary={s:analyze(s) for s in ("dev","test")};summary["splits"]={k:[len(v),len({r["t"] for r in v})] for k,v in load(b.OFF/"split.json.gz").items()};summary["training_file_bytes"]=(D/"numeric-train.npz").stat().st_size
    save(D/"audit.json",summary);print(summary)
if __name__=="__main__":main()