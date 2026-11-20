"""Open gold only after classifier/lexical predictions have been sealed. Bootstrap paired queries by repository."""
import gzip,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
import numpy as np
import pyarrow.parquet as pq
from data_io import D,read,write,files,panel_name,sha,gz

# Public table counts per panel [BM25 @1, @5; Semlith @1, @5] -- 500 rows each.
EXTERNAL={
"java_cff_test_easy":{3:(81,408,84,417),10:(67,402,61,414)},"java_cff_test_hard":{3:(51,216,56,255),10:(43,190,38,223)},
"java_cfr_test_easy":{3:(130,414,140,437),10:(113,421,115,432)},"java_cfr_test_hard":{3:(100,285,96,319),10:(81,296,86,294)},
"python_cff_test_easy":{3:(108,401,126,425),10:(95,399,125,420)},"python_cff_test_hard":{3:(65,245,90,248),10:(63,223,82,259)},
"python_cfr_test_easy":{3:(132,429,149,439),10:(135,428,131,424)},"python_cfr_test_hard":{3:(106,289,143,312),10:(105,300,114,300)}}
def metric(order,costs,gold):
    r=1+order.index(gold) if gold in order else 1000000
    used=0;pack=[]
    for j in order:
        add=costs[j]+bool(pack)
        if used+add<=512:
            pack.append(j);used+=add
            if len(pack)==3:break
    return [int(r==1),int(r<=3),int(r<=5),1/r if r<1000000 else 0,int(gold in pack),used]
def summary(items,arms):
    A={a:np.array([i[-1][a] for i in items]) for a in arms}
    projects=sorted({r[3] for r in items});idx={x:j for j,x in enumerate(projects)}
    labels=np.array([idx[r[3]] for r in items])
    cnt=np.bincount(labels)
    stats={a:{k:(A[a][:,j].mean() if j==3 or j==5 else int(A[a][:,j].sum())) for j,k in enumerate(["hits1","hits3","hits5","mrr","packed512","mean_tokens"])} for a in arms}
    diffs={}
    for new,old in [('graph','owner'),('graph','local'),('local','flat'),('graph','flat'),('graph','permute'),('owner','flat'),('graph','publisher_bm25'),('graph','binary')]:
        if new not in A or old not in A:continue
        d=A[new]-A[old];s=np.vstack([np.bincount(labels,weights=d[:,j],minlength=len(cnt)) for j in range(5)]).T
        rng=np.random.default_rng(7112026);bs=[]
        for _ in range(20):
            ix=rng.integers(len(cnt),size=(500,len(cnt)));bs.extend((s[ix].sum(axis=1)/cnt[ix].sum(axis=1)[:,None]).tolist())
        diffs[new+"-"+old]={"delta":d[:,:5].mean(axis=0).tolist(),"ci":np.quantile(bs,[.025,.975],axis=0).tolist(),
          "equal_project":(s/cnt[:,None]).mean(axis=0).tolist(),"w":int((d[:,0]>0).sum()),"l":int((d[:,0]<0).sum())}
    return {"n":len(items),"projects":len(cnt),"invalid":sum(i[6] for i in items),"rows_with_edges":sum(i[5]>0 for i in items),"stats":stats,"diff":diffs}
def main():
    alerts={};summary_all={};natives={}
    for key,p in read("prediction_lock.json")["files"].items():assert sha(D/key)==p
    for l,h in read("lexical_lock.json")["sha256"].items():assert sha(D/("lexical_"+l+".jsonl.gz"))==h
    native={}
    if (D/"native_predictions.json").is_file():
        native={(q,i,k):r for q,i,k,z,r in read("native_predictions.json")}
        assert len(native)==192
    for lang in ("java","python"):
        allgold=defaultdict(list)
        for p in files(lang,"test"):
            allgold[panel_name(p.stem)].extend(pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist())
        lex={(q,j,k):a for q,j,k,a in gz(D/("lexical_"+lang+".jsonl.gz"))}
        scored=[]
        for panel,j,k,repo,cost,h,cnt,arms in gz(D/(lang+".pred.jsonl.gz")):
            g=allgold[panel][j];arms["publisher_bm25"]=lex[panel,j,k]
            if (panel,j,k) in native:arms["binary"]=native[panel,j,k]
            for name,rank in arms.items():assert sorted(rank)==list(range(len(cost)))
            score={a:metric(r,cost,g) for a,r in arms.items()}
            scored.append([panel,j,k,repo,h,cnt,int(not 0<=g<len(cost)),score])
        with gzip.open(D/(lang+".scores.jsonl.gz"),"wt",encoding="utf8") as f:
            for i in scored:f.write(json.dumps(i,separators=(",",":"))+"\n")
        mainarms=["flat","local","owner","graph","permute","publisher_bm25"]
        for k in (3,10):
            rr=[i for i in scored if i[2]==k]
            summary_all[lang+str(k)]=summary(rr,mainarms)
            bins={}
            for panel in sorted({i[0] for i in rr}):
                group=[i for i in rr if i[0]==panel];matched={}
                for a in mainarms:
                    matched[a]=[sum(i[-1][a][j] for i in group) for j in (0,2)]
                vals=EXTERNAL[panel][k];alerts[panel+str(k)]=dict(official_bm25=vals[:2],observed=matched["publisher_bm25"],match=list(vals[:2])==matched["publisher_bm25"])
                matched["published_semlith"]=vals[2:];bins[panel]=matched
            summary_all[lang+str(k)]["strata"]=bins
            subset=[i for i in rr if "binary" in i[-1]]
            if subset:natives[lang+str(k)]=summary(subset,[*mainarms,"binary"])
    write("results.json",summary_all);write("native_results.json",natives)
    write("comparison_audit.json",alerts)
    assert all(v["match"] for v in alerts.values()),alerts
if __name__=="__main__":main()
