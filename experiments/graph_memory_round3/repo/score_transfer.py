from score import summarize,contrast
from io_utils import D,read,save,sha,load_gz,dump,np,gzip
import pyarrow.parquet as pq
from collections import Counter
def main():
    for f,h in read("transfer_method_lock.json")["sha"].items():assert sha(D/f)==h
    for f,h in read("transfer_predictions_lock.json")["sha"].items():assert sha(D/f)==h
    labels={p.name:pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist() for p in (D/"transfer_inputs").glob("*.parquet")}
    rows=[];gates=[];anom=[]
    for fname,i,r,h,ln,lens,g,ranks in load_gz(D/"transfer_predictions.jsonl.gz"):
        target=labels[fname][i];rep="random" if "random" in fname else "first";n=len(lens)
        assert all(sorted(ind)==list(range(n)) for ind in ranks.values())
        if not 0<=target<n:anom.append([fname,i,target,n])
        ranks["oracle_type"]=ranks[rep];hit={a:(rank.index(target)+1 if 0<=target<n else 100000+n+1) for a,rank in ranks.items()}
        rows.append([rep,i,r,h,hit,{a:lens[v[0]] for a,v in ranks.items()}]);gates.append([g,rep=="random",ln,n])
    res={}
    for k,rs in [("all",rows),("first",[r for r in rows if r[0]=="first"]),("random",[r for r in rows if r[0]=="random"])]:
        names=rs[0][4]
        res[k]={"n":len(rs),"repos":len(set(r[2] for r in rs)),"metrics":{a:{"hits":[sum(r[4][a]<=j for r in rs) for j in (1,3,5)],"mrr":sum(1/r[4][a] if r[4][a]<100000 else 0 for r in rs)/len(rs)} for a in names},
                "paired":{f"{a}-{b}":contrast(rs,a,b) for a,b in (("gate","mix"),("gate","transition"),("transition","owner"),("transition","placebo"))}}
    pro=np.array([q for q,y,ln,n in gates]);ys=np.array([y for q,y,ln,n in gates]);lines=np.array([ln for q,y,ln,n in gates]);sizes=np.array([n for q,y,ln,n in gates])
    res["gate"]={"type_accuracy":float(np.mean((pro>=.5)==ys)),"brier":float(np.mean((pro-ys)**2)),"constant_brier":.25,"prefix_line_quartiles":np.quantile(lines,[0,.25,.5,.75,1]).tolist(),"slate_quartiles":np.quantile(sizes,[0,.25,.5,.75,1]).tolist(),"malformed":anom}
    with gzip.open(D/"transfer_scores.jsonl.gz","wt",encoding="utf8") as f:
        for r in rows:dump(f,r)
    save("transfer_results.json",res)
    gold0={p.stem:pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist() for p in (D/"inputs").glob("*test*.parquet")}
    from_orig={(r[0],r[1]):r for r in load_gz(D/"scores.jsonl.gz")}
    clean=[]
    for p,i,ranks in load_gz(D/"clean_predictions.jsonl.gz"):
        g=gold0[p][i];r=from_orig[p,i]
        clean.append([p,i,r[2],r[3],{a:(R.index(g)+1 if g in R else 100000+len(R)+1) for a,R in ranks.items()},{}])
    save("clean_results.json",{"n":len(clean),"hits":{a:sum(r[4][a]==1 for r in clean) for a in clean[0][4]},"paired":contrast(clean,"transition","owner"),"invalid_count":len(read("transfer_fit.json")["invalid_train"])})
if __name__=="__main__":main()
