"""Grade deterministic and exactly marginalized random-thinning policies with paired clusters."""
from collections import Counter
import math
import unicodedata
import numpy as np
from setup import *

PAIRS=[("real_salience",a) for a in ("text_salience","text_proxy","text_top","real_top","real_original")]+[
       ("real_top","text_top"),("real_random","text_random"),("real_original","text_original")]
def canon(s):return unicodedata.normalize("NFC"," ".join(s.replace("_"," ").split()))
def marginal(pool,k,score):
    if len(pool)==1:return score(pool[0])
    n=len(pool);assert 1<=k<=n
    w=k/n;vals=[0.,0.];total=0.
    for j,i in enumerate(pool[:n-k+1]):
        x=score(i);vals[0]+=w*x[0];vals[1]+=w*x[1];total+=w
        if j!=n-k:w*= (n-j-k)/(n-j-1)
    assert abs(total-1)<1e-10
    return vals
def bootstrap(matrix,seeds):
    _,idx=np.unique(seeds,return_inverse=True);g=idx.max()+1
    count=np.bincount(idx,minlength=g);total=np.array([np.bincount(idx,weights=v,minlength=g) for v in matrix.T]).T
    rng=np.random.default_rng(530223);runs=10000;sim=np.empty((runs,matrix.shape[1]))
    for lo in range(0,runs,64):
        n=min(64,runs-lo);draw=rng.integers(0,g,size=(n,g))
        sim[lo:lo+n]=total[draw].sum(axis=1)/count[draw].sum(axis=1)[:,None]
    return (np.quantile(sim,[.025,.975],axis=0)*100).T
def evaluate(p,seal,names):
    qmap=read(D/(p+"-choices.json.gz"));src=SPLITS[p][0];truth=read(src/("gold.json.gz" if p=="hotpot" else "support.json.gz"))
    assert set(qmap)==set(truth)
    arms=seal["arms"];rows={};sizes=[];seedids=[];flags=[];values=[]
    for q,r in sorted(qmap.items()):
        gs=set(truth[q][1]);s=canon(names[str(r["seed"])]);h,l,k,intersection=r["sizes"]
        def hit(i):
            v=len({s,canon(names[str(i)])}&gs);return (int(v==len(gs)),v/len(gs))
        raw=dict(zip(seal["fixed"],[hit(i) for i in r["fixed"]]))
        raw["real_random"],raw["text_random"]=[marginal(d,k,hit) for d in r["random"]]
        vec=[raw[a] for a in arms];rows[q]=vec;values.append(vec);sizes.append(r["sizes"]);seedids.append(r["seed"]);flags.append(r["direct"])
    v=np.asarray(values);s=np.asarray(sizes);seedids=np.asarray(seedids);flags=np.asarray(flags)
    def summary(mask):
        x=s[mask];ns=len(x)
        return dict(n=ns,means=dict(zip(arms,v[mask].mean(axis=0).tolist())),candidate_mean=x.mean(axis=0).tolist(),
                  candidate_median=np.median(x,axis=0).tolist(),candidate_totals=x.sum(axis=0).tolist(),
                  no_href=int((x[:,0]==0).sum()),no_literal=int((x[:,1]==0).sum()),k_zero=int((x[:,2]==0).sum()),
                  href_larger=int((x[:,0]>x[:,1]).sum()),href_smaller=int((x[:,0]<x[:,1]).sum()))
    allrows=np.ones(len(v),dtype=bool);sub={"all":summary(allrows),"fallback":summary(~flags),"fallback_both":summary((~flags)&(s[:,2]>0))}
    descriptions={};keys=[];columns=[]
    for a,b in PAIRS:
        for j,m in enumerate(["full","recall"]):
            keys.append((a,b,m));columns.append(v[:,arms.index(a),j]-v[:,arms.index(b),j])
    differences=np.column_stack(columns);bounds=bootstrap(differences,seedids)
    for j,(a,b,m) in enumerate(keys):
        diff=differences[:,j];bound=bounds[j]
        d=dict(delta_pp=float(diff.mean()*100),ci95_pp=bound.tolist(),wins=int((diff>1e-12).sum()),losses=int((diff< -1e-12).sum()))
        descriptions.setdefault(a+"-"+b,{})[m]=d
    return rows,dict(n=len(v),unique_first=len(set(seedids.tolist())),size_columns=["href","literal","matched_k","intersection"],summary=sub,contrasts=descriptions)
def main(verify=False):
    seal=read(D/"prediction-seal.json");assert all(sha(D/f)==v for f,v in seal["files"].items());names=read(D/"titles.json.gz")
    result={}
    for p in ["hotpot","2wiki"]:
        rows,o=evaluate(p,seal,names);result[p]=o
        if verify:assert rows==read(D/(p+"-outcomes.json.gz")) or json.dumps(rows,sort_keys=True)==json.dumps(read(D/(p+"-outcomes.json.gz")),sort_keys=True)
        else:save(D/(p+"-outcomes.json.gz"),rows)
    if verify:assert result==read(D/"results.json")
    else:
        save(D/"results.json",result);save(D/"grading-seal.json",dict(prediction=sha(D/"prediction-seal.json"),results=sha(D/"results.json"),code=sha(Path(__file__)),
            support={p:sha(SPLITS[p][0]/("gold.json.gz" if p=="hotpot" else "support.json.gz")) for p in result},
            outcomes={p:sha(D/(p+"-outcomes.json.gz")) for p in result}))
    for p,r in result.items():
        print(p,r["n"],r["summary"]["fallback_both"]["n"],r["contrasts"]["real_salience-text_salience"]["full"],r["contrasts"]["real_salience-text_proxy"]["full"],flush=True)
if __name__=="__main__":
    import sys
    main("--verify" in sys.argv)
