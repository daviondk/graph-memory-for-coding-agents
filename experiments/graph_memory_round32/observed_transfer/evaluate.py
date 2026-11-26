"""Join supporting titles after freezing predictions. Bootstrap questions and repeated gold sets."""
from collections import Counter,defaultdict
import hashlib
import numpy as np
from transfer import ROOT,SRC,get,put,sha,pq,json

def ci(rows):
    x=np.asarray(rows,dtype=float)
    rng=np.random.default_rng(320041)
    sims=np.concatenate([x[rng.integers(len(x),size=(50,len(x)))].mean(axis=1) for _ in range(200)])
    return [float(v) for v in np.quantile(100*sims,[.025,.975])]

def cluster_ci(delta,groups):
    grouped=defaultdict(list)
    for v,g in zip(delta,groups):grouped[g].append(v)
    totals=np.array([[sum(v),len(v)] for v in grouped.values()])
    rng=np.random.default_rng(320042);sims=[]
    for _ in range(200):
        sums=totals[rng.integers(len(totals),size=(50,len(totals)))].sum(axis=1)
        sims.extend(100*sums[:,0]/sums[:,1])
    return [float(v) for v in np.quantile(sims,[.025,.975])]
def main():
    seal=get(ROOT/"seal.json");assert sha(ROOT/"predictions.json.gz")==seal["predictions"] and sha(ROOT/"plan.json")==seal["plan"]
    assert sha(SRC)==get(ROOT/"plan.json")["source"]
    pred=get(ROOT/"predictions.json.gz");rows={}
    for batch in pq.ParquetFile(SRC).iter_batches(batch_size=256,columns=["_id","context","supporting_facts","type"]):
        for r in batch.to_pylist():
            q=r["_id"];arm=pred[q];cat=json.loads(r["context"])
            titles=[cat[i][0] for i in arm["order"]];gold={x[0] for x in json.loads(r["supporting_facts"])}
            assert gold and q not in rows
            counts={m:len(gold & {titles[arm["seed"]],titles[j]}) for m,j in arm["next"].items()}
            rows[q]={"g":len(gold),"group":hashlib.sha256(json.dumps(sorted(gold),ensure_ascii=False).encode()).hexdigest(),
                     "hits":counts,"seed_hit":int(titles[arm["seed"]] in gold),"type":r["type"],"missing":len(gold-set(titles)),"tokens":arm["tokens"]}
    assert set(rows)==set(pred);two=[v for v in rows.values() if v["g"]==2]
    def table(values):
        return {m:{"both":sum(r["hits"][m]==2 for r in values),"recall_pct":100*np.mean([r["hits"][m]/r["g"] for r in values]),"mean_hits":np.mean([r["hits"][m] for r in values])} for m in two[0]["hits"]}
    def contrast(cases):
        delta=[int(r["hits"]["local_static"]==2)-int(r["hits"]["mention_title"]==2) for r in cases];groups=[r["group"] for r in cases]
        return {"pp":100*np.mean(delta),"wins":delta.count(1),"losses":delta.count(-1),"ci_question":ci(delta),"ci_gold_cluster":cluster_ci(delta,groups),"clusters":len(set(groups))}
    types=sorted({r["type"] for r in two})
    put(ROOT/"outcomes.json.gz",rows)
    put(ROOT/"results.json",{"n":len(rows),"n_two":len(two),"n_missing_any":sum(bool(r["missing"]) for r in rows.values()),"seed_two":sum(r["seed_hit"] for r in two),
           "source_counts":dict(Counter(r["g"] for r in rows.values())),"all":table(rows.values()),"two":table(two),"primary":contrast(two),
           "two_by_type":{t:{"n":len(group),"scores":table(group)} for t in types if (group:=[v for v in two if v["type"]==t])},
           "mean_tokens":np.mean([r["tokens"] for r in rows.values()]),"max_tokens":max(r["tokens"] for r in rows.values()),"outcomes":sha(ROOT/"outcomes.json.gz")})
if __name__=="__main__":main()
