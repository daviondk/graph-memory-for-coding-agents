"""Reorder whole BGE pools; choose lambda from labeled development only."""
from common import D, UP, PUB, data, get, native, np, rows, save, sha

def sequences(values, rel, lambdas):
    pairwise=values @ values.T
    base=np.argsort(-rel,kind="stable")
    variants={}
    for lam in lambdas:
        ranks=[int(base[0])]; selected=set(ranks)
        while len(ranks)<min(8,len(rel)):
            utility=lam*rel-(1-lam)*pairwise[:,ranks].max(axis=1)
            idx=min((i for i in range(len(rel)) if i not in selected),key=lambda i:(-utility[i],i))
            ranks.append(idx);selected.add(idx)
        variants[lam]=ranks
    assert variants[1.0]==base[:8].tolist()
    return variants

def complete(ids, label, k):
    chosen=set(ids[:k])
    groups=label["required_evidence_groups"]
    return int(all(native.group_completion_rank(ids,g,k) is not None for g in groups)
               or any(set(a)<=chosen for a in label["alternative_minimal_sets"]))

def main():
    features=data(); vec=UP/"dense_vectors.npy"; assert sha(vec)==get(UP/"dense_runtime.json")["vectors_sha256"]
    v=np.load(vec,mmap_mode="r"); layouts={r["state_id"]:r for r in rows(UP/"dense_inputs.jsonl.gz")}
    lambdas=(.25,.5,.75,1.0)
    dev={sid for sid,r in features.items() if r["split"]=="dev"}
    labels={x["state_id"]:x for x in rows(PUB/"labels.jsonl.gz") if x["state_id"] in dev}
    assert len(dev)==len(labels)==101
    counts={l:0 for l in lambdas}; pred={}
    for sid,fr in sorted(features.items()):
        if fr["split"]=="train":continue
        layout=layouts[sid]; mapping=dict(layout["candidates"])
        vals=v[[mapping[i] for i in fr["ids"]]].astype(np.float32);vals/=np.linalg.norm(vals,axis=1,keepdims=True)
        q=v[layout["queries"]["state"]].astype(np.float32);q/=np.linalg.norm(q)
        alts=sequences(vals,vals @ q,lambdas)
        assert alts[1.0]==np.argsort(fr["ranks"]["dense_state"])[:8].tolist()
        if sid in dev:
            for l,order in alts.items():
                ids=[fr["ids"][i] for i in order]
                counts[l]+=complete(ids,labels[sid],5)
        else:pred[sid]=alts
    selected=max(counts,key=lambda l:(counts[l],l))
    save(D/"mmr-dev.json",dict(counts=counts,selected=selected,n=len(dev),vectors=sha(vec)))
    save(D/"mmr-predictions.json.gz",{s:x[selected] for s,x in pred.items()})
    print("dev",counts,"chosen",selected)
if __name__=="__main__":main()
