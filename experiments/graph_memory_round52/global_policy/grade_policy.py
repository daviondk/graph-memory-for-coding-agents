"""Read annotations only after all sibling submissions are frozen, verifying both seals first."""
from collections import Counter, defaultdict
from pathlib import Path
import sys
import unicodedata
import numpy as np
from seal_policy import HERE, BASE, GATES, OUTPUTS, read, save, hashfile

def canon(text):
    return unicodedata.normalize("NFC"," ".join(text.replace("_"," ").split()))

def summarize(a, index):
    return dict(n=len(index),hits=dict(zip(OUTPUTS,a[index].sum(axis=0).tolist())))

def main():
    frozen=read(HERE/"prediction-seal.json")
    assert hashfile(HERE/"prediction-seal.json")=="83beb87a77255f4328fe342592b05bf4499922defe6da597f9257e7090c911a5"
    for k,v in frozen["local"].items():
        assert hashfile(HERE/k)==v
    sibling=read(BASE/"prediction-seal.json")
    assert all(hashfile(BASE/k)==v for k,v in sibling["files"].items())
    pred=read(HERE/"predictions.json.gz")
    labels=read(BASE/"support.json.gz")
    names=read(HERE/"chosen-titles.json.gz")
    assert set(pred)==set(labels) and len(pred)==12576
    joint=read(BASE/"predictions.json.gz")
    parent_names=read(BASE/"chosen-titles.json.gz")
    sys.path.insert(0,str(BASE))
    from seal import ARMS
    subsets=defaultdict(list);seeds=[];matrix=[];recalls=[];audited={};first_hit=0
    for i,k in enumerate(sorted(pred)):
        p=pred[k]
        seed=p["seed"];seeds.append(seed)
        source=canon(names[str(seed)][1])
        sibling_row=joint[k]
        assert seed==sibling_row[0] and canon(parent_names[str(seed)][1])==source
        for here,there in (("free","free"),("parent_text","text"),("parent_href","href"),
                           ("text_first","text_first"),("href_first","href_first")):
            assert p["choices"][OUTPUTS.index(here)]==sibling_row[2][ARMS.index(there)]
        question_type, gold=labels[k];gold=set(gold)
        first_hit+=int(source in gold)
        # All policies can read only the seed plus their selected second address.
        count=[len({source,canon(names[str(c)][1])}&gold) for c in p["choices"]]
        full=[int(n==len(gold)) for n in count]
        matrix.append(full);recalls.append([n/len(gold) for n in count])
        audited[k]=[len(gold),full,count]
        subsets["type:"+question_type].append(i)
        subsets["supports:"+str(len(gold))].append(i)
        for j,gate in enumerate(GATES):
            label="direct" if p["gates"][j][1] else "bridge"
            subsets[gate+":"+label].append(i)
    a=np.asarray(matrix,dtype=np.int8)
    contrasts=[(g+"_href",g+"_text") for g in GATES]
    contrasts += [("primary_href", k) for k in ("href_first","text_first","parent_href","primary_free","free")]
    contrasts += [("primary_text",k) for k in ("text_first","parent_text")]
    unique,ix=np.unique(seeds,return_inverse=True)
    denom=np.bincount(ix)
    counts=[]; diffs=[]
    for left,right in contrasts:
        d=a[:,OUTPUTS.index(left)]-a[:,OUTPUTS.index(right)]
        counts.append(np.bincount(ix,weights=d))
        diffs.append(d)
    totals=np.asarray(counts).T
    draws=[];rng=np.random.default_rng(520117)
    for _ in range(100):
        inds=rng.integers(len(unique),size=(100,len(unique)))
        draws.append(totals[inds,:].sum(axis=1)/denom[inds].sum(axis=1)[:,None])
    bounds=np.quantile(np.vstack(draws),[.025,.975],axis=0)
    report={"arms":OUTPUTS,"n":len(a),"first_sources":len(unique),"seed_hits":first_hit,
            "complete":dict(zip(OUTPUTS,a.sum(0).tolist())),"support_recall":dict(zip(OUTPUTS,np.mean(recalls,axis=0).tolist())),
            "subsets":{k:summarize(a,v) for k,v in subsets.items()},
            "contrast":{l+" vs "+r:{"delta":float(d.mean()),"ci95":bounds[:,j].tolist(),"wins":int((d>0).sum()),
                       "losses":int((d<0).sum()),"ties":int((d==0).sum())} for j,((l,r),d) in enumerate(zip(contrasts,diffs))},
            "parent_support_sha256":hashfile(BASE/"support.json.gz"),
            "forecast_seal_sha256":hashfile(HERE/"prediction-seal.json")}
    save(HERE/"results.json",report)
    save(HERE/"graded-rows.json.gz",audited)
    print(report["complete"])
    print(report["contrast"])

if __name__=="__main__":
    main()

