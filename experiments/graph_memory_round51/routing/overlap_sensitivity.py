"""Sensitivity to repeated evidence, by connected components of actually selected documents."""
import hashlib
import numpy as np
from study import D,T,P,FIRST,get,put,sha


def summarize(path,private,arm,control,name):
    data=get(private/"visible.json.gz")
    ctx=get(path/"contexts.json.gz")
    out=get(path/"outcomes.json.gz")
    choices=get(D/"router-choices.json.gz") if arm=="router" else {}
    roster=sorted(out)
    parent={q:q for q in roster}
    by_document={}
    doc_ids={}
    def root(q):
        while parent[q]!=q:
            parent[q]=parent[parent[q]]
            q=parent[q]
        return q
    for q in roster:
        r=ctx[q];base=r["refs"][control][0]
        target=choices[q]["address"] if arm=="router" else r["refs"][arm][0]
        union=sorted({r["seed"],base,target})
        ids=[]
        for i in union:
            _,title,body=data[q][1][i]
            h=hashlib.sha256((title+"\0"+body).encode()).hexdigest()
            ids.append(h)
            prev=by_document.setdefault(h,q)
            parent[root(q)]=root(prev)
        doc_ids[q]=ids
    put(D/(name+"-selected-documents.json.gz"),doc_ids)
    groups={}
    for q in roster:
        groups.setdefault(root(q),[]).append(out[q]["arms"][arm][1]-out[q]["arms"][control][1])
    g=list(groups.values())
    sums=np.array([sum(x) for x in g]);sizes=np.array(list(map(len,g)))
    draws=[]
    rng=np.random.default_rng(510037)
    for _ in range(100):
        sample=rng.integers(len(g),size=(100,len(g)))
        draws.extend(sums[sample].sum(1)/sizes[sample].sum(1))
    return dict(arm=arm,control=control,n=len(roster),components=len(g),biggest=max(map(len,g)),
        multi=sum(len(x)>1 for x in g),queries_in_multi=sum(len(x) for x in g if len(x)>1),
        nonzero_components=int((np.abs(sums)>1e-12).sum()),pp=100*float(sums.sum())/len(roster),
        cluster_ci=(100*np.quantile(draws,[.025,.975])).tolist(),seed=510037,
        output_hash=sha(path/"outcomes.json.gz"),hashes=sha(D/(name+"-selected-documents.json.gz")))


if __name__=="__main__":
    results={"hotpot_640":summarize(T,FIRST,"adaptive","dense","transfer"),
             "hotpot_1280":summarize(D,P,"router","linked_dense","routing")}
    put(D/"overlap-sensitivity.json",results)
    print(results)
