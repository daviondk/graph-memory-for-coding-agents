"""Compare sparse and deque directly as an exploratory robustness contrast."""
from collections import defaultdict
import numpy as np
from bench import D,PAR,read,save,sha

def main():
    qids=read(D/"plan.json")["ids"];labels=read(PAR/"build-rows.json.gz")
    records={m:{q:[] for q in qids} for m in ("sparse","deque")}
    for m,items in records.items():
        for rep in range(3):
            run=read(D/"runs"/f"native-{m}-{rep}.json.gz")
            for q,(ns,k,h) in run["rows"].items():items[q].append([ns,k])
    mat=np.array([[np.median(records[m][q],axis=0) for m in ("sparse","deque")] for q in qids])
    groups=[[i for i,q in enumerate(qids) if labels[q]["article"]==t] for t in sorted({v["article"] for v in labels.values()})]
    def contrast(x):return np.median(x[:,0],axis=0)/np.median(x[:,1],axis=0)
    rng=np.random.default_rng(29683)
    draws=[contrast(mat[np.concatenate([groups[i] for i in s])]) for s in rng.integers(len(groups),size=(10000,len(groups)))]
    result={"native":sha(D/"native-results.json"),"analysis":sha(D/"alternative.py"),"ratio_sparse_over_deque":contrast(mat).tolist(),
            "ci":np.percentile(draws,[2.5,97.5],axis=0).T.tolist(),"units":["end_to_end","kernel"]}
    save(D/"alternative.json",result);print(result)
if __name__=="__main__":main()
