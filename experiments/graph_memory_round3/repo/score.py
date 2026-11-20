"""Evaluate orders frozen before opening test targets. The next-line text is never loaded."""
from collections import Counter,defaultdict
import gzip
import numpy as np
import pyarrow.parquet as pq
from io_utils import D,read,save,sha,load_gz,dump
def contrast(rows,a,b):
    buckets=defaultdict(list);wins=losses=0
    for panel,i,repo,q,ranks,lens in rows:
        d=int(ranks[a]==1)-int(ranks[b]==1);wins+=d==1;losses+=d==-1;buckets[repo].append(d)
    projs=sorted(buckets);n=np.array([len(buckets[r]) for r in projs])
    total=np.array([sum(buckets[r]) for r in projs]);bs=np.random.default_rng(261118).integers(len(n),size=(10000,len(n)))
    ci=np.quantile(total[bs].sum(axis=1)/n[bs].sum(axis=1),[.025,.975])
    return dict(delta=(wins-losses)/len(rows),wins=wins,losses=losses,ci=ci.tolist(),macro=float((total/n).mean()),positive=int((total>0).sum()),negative=int((total<0).sum()),equal=int((total==0).sum()))
def summarize(rows):
    arms=list(rows[0][4]);n=len(rows)
    def metrics(a):
        r=np.array([row[4][a] for row in rows]);cost=np.array([row[5][a] for row in rows])
        return dict(hits=[int((r<=k).sum()) for k in [1,3,5]],mrr=float(np.where(r<100000,1/r,0.).mean()),mean_rank=float(np.mean([v if v<100000 else v-100000 for v in r])),chars=float(cost.mean()))
    return dict(n=n,repo=len({r[2] for r in rows}),metrics={a:metrics(a) for a in arms},
                paired={a:contrast(rows,"transition",a) for a in ["flat","owner","placebo","jaccard3"]})
def main():
    for n,h in read("method_lock.json")["sha256"].items():assert sha(D/n)==h
    for n,h in read("predictions_lock.json")["sha256"].items():assert sha(D/n)==h
    rows=[];output={}
    for f in sorted(D.glob("*.pred.jsonl.gz")):
        stem=f.name.split(".pred")[0];gold=pq.read_table(D/"inputs"/(stem+".parquet"),columns=["gold_snippet_index"]).column(0).to_pylist()
        subset=[]
        for i,repo,q,lens,ranks in load_gz(f):
            g=gold[i];n=len(lens)
            assert all(sorted(indices)==list(range(n)) for indices in ranks.values())
            subset.append([stem,i,repo,q,{a:(rank.index(g)+1 if 0<=g<n else 100000+n+1) for a,rank in ranks.items()},{a:lens[rank[0]] for a,rank in ranks.items()}])
        assert len(subset)==len(gold);rows.extend(subset);output[stem]=summarize(subset)
    with gzip.open(D/"scores.jsonl.gz","wt",encoding="utf8") as f:
        for x in rows:dump(f,x)
    output["all"]=summarize(rows)
    for level in ("easy","hard"):output[level]=summarize([r for r in rows if level in r[0]])
    unique={};counts=Counter((r[2],r[3]) for r in rows)
    for r in rows:unique.setdefault((r[2],r[3]),r)
    output["dedup"]=summarize(list(unique.values()))
    output["duplicate_count"]=sum(v-1 for v in counts.values())
    save("results.json",output)
if __name__=="__main__":main()

