"""Post hoc sensitivity: template types, repeated evidence and clusters sharing any gold title."""
from pipeline import ROOT,IN,CACHE,loadgz,dump
from collections import Counter,defaultdict
import json
import numpy as np
import pyarrow.parquet as pq

def norm(s):return " ".join(s.casefold().split())
def main():
    first=[r for r in loadgz(ROOT/"transfer_item_scores.jsonl.gz") if r["dataset"]=="w2"]
    rep=loadgz(ROOT/"typed_item_scores.jsonl.gz")
    source={r["_id"]:r for r in pq.read_table(IN/"2wiki-dev.parquet",columns=["_id","question","type","supporting_facts"]).to_pylist()}
    train=set(json.loads((CACHE/"train_gold.json").read_text(encoding="utf8")))
    hot={norm(r["question"]) for r in pq.read_table(IN/"train-half.parquet",columns=["id","question"]).to_pylist() if r["id"] in train}
    def q(r):return norm(source[r["id"]]["question"])
    def docs(r):return tuple(sorted({norm(t) for t,i in json.loads(source[r["id"]]["supporting_facts"])}))
    previous_q={q(r) for r in first};previous_docs={docs(r) for r in first}
    def deltas(name,rows):
        d=np.array([r["hits"]["roles"]-r["hits"]["graph"] for r in rows])
        return {"n":len(d),"graph":sum(r["hits"]["graph"] for r in rows),"roles":sum(r["hits"]["roles"] for r in rows),
                "wins":int((d==1).sum()),"losses":int((d==-1).sum()),"delta":float(d.mean())}
    by_type=defaultdict(list)
    for r in rep:by_type[source[r["id"]]["type"]].append(r)
    freq=Counter(q(r) for r in rep)
    parent={}
    def root(t):
        parent.setdefault(t,t)
        while t!=parent[t]:
            parent[t]=parent[parent[t]];t=parent[t]
        return t
    for r in rep:
        a,b=docs(r); a=root(a);b=root(b)
        if a!=b:parent[a]=b
    groups=[root(docs(r)[0]) for r in rep]; gg,ix=np.unique(groups,return_inverse=True)
    d=np.array([r["hits"]["roles"]-r["hits"]["graph"] for r in rep])
    sums=np.bincount(ix,weights=d);nums=np.bincount(ix);rng=np.random.default_rng(261118);draw=[]
    for _ in range(100):
        ix0=rng.integers(len(gg),size=(100,len(gg)));draw.extend(sums[ix0].sum(1)/nums[ix0].sum(1))
    novel=[r for r in rep if q(r) not in previous_q and docs(r) not in previous_docs and q(r) not in hot]
    result={"preexisting_question_in_hotpot_train":sum(q(r) in hot for r in rep),"question_in_previous_2k":sum(q(r) in previous_q for r in rep),
        "gold_pair_in_previous_2k":sum(docs(r) in previous_docs for r in rep),"distinct_question_strings":len(freq),
        "distinct_gold_pairs":len(set(docs(r) for r in rep)),"no_repeated_q_or_evidence_pair_from_previous":deltas("novel",novel),
        "type_breakdown":{t:deltas(t,rows) for t,rows in by_type.items()},"shared_gold_title_components":len(gg),"largest_component":int(nums.max()),
        "component_cluster_95ci":np.quantile(draw,[.025,.975]).tolist()}
    dump(result,"replication_sensitivity.json");print(json.dumps(result))
if __name__=="__main__":main()
