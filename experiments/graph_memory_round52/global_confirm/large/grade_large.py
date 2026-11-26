"""Paired results for the untouched 12k, with retrospective 2400 template-control diagnosis."""
from collections import Counter,defaultdict
from pathlib import Path
from zipfile import ZipFile
import json
import sys
import numpy as np
import pyarrow.parquet as pq
from large_panel import HERE,S,CONF,C_S,PAR,R50,read,save,hashfile
from large_predictions import ARMS,score
from grade_confirmation import title

PAIRS=[("learned_dev",k) for k in ("coord_cautious","coord_or_same_as","dev_tree","primary_href")]
PAIRS.extend([("coord_or_same_as","coord_cautious"),("dev_tree","coord_cautious"),("dev_tree","coord_or_same_as"),
              ("primary_href","primary_text")])

def gold_from_authors(sel):
    source=read(R50.parent/"qa_external/official-source.json")
    archive=Path("D:/CodexResearch/x20-r50-qa-external/data_ids.zip")
    assert hashfile(archive)==source["archive"] and hashfile(PAR)==read(HERE/"sampling.json")["source_sha256"]
    mirror={}
    for batch in pq.ParquetFile(PAR).iter_batches(columns=["_id","type","supporting_facts"]):
        for row in batch.to_pylist():
            q=row["_id"]
            if q not in sel:continue
            s=row["supporting_facts"];s=json.loads(s) if isinstance(s,str) else s
            ts=s["title"] if isinstance(s,dict) else [v[0] if isinstance(v,list) else v["title"] for v in s]
            mirror[q]=[row["type"],sorted(set(map(title,ts)))]
    sys.path.insert(0,str(R50))
    from stream_json import iter_array
    authors={}
    with ZipFile(archive) as z,z.open("data_ids/train.json") as f:
        for row in iter_array(f):
            q=row["_id"]
            if q in sel:
                assert row["question"]==sel[q]
                authors[q]=[row["type"],sorted({title(t) for t,_ in row["supporting_facts"]})]
    assert len(authors)==len(sel) and authors==mirror
    save(HERE/"support.json.gz",authors)
    save(HERE/"truth-receipt.json",{"n":len(authors),"official_zip":source["archive"],"train_parquet":hashfile(PAR),
                                   "previous_disjoint":True,"seal":hashfile(HERE/"prediction-seal.json")})
    return authors

def retrospective():
    model=read(CONF/"dev-model.json");tree=read(HERE/"dev-tree.json");qtext=read(C_S/"questions.json.gz")
    old=read(CONF/"predictions.json.gz");names=read(CONF/"chosen-titles.json.gz")
    res={}
    for q,r in old.items():
        v=r["choices"];row=score(qtext[q],names[str(r["seed"])][1],r["direct_gate"],v[2],v[3],model,tree)
        assert [row["choices"][i] for i in (0,1,4,5,6)]==[v[i] for i in (8,7,0,1,2)]
        res[q]={**row,"seed":r["seed"]}
    return res,names,read(CONF/"support.json.gz")

def grade(pred,names,gold):
    ticks=[];wins=[];recs=[];choices=[];groups=defaultdict(list);cases={}
    for i,q in enumerate(sorted(pred)):
        r=pred[q];source=title(names[str(r["seed"])][1]);kind,g=gold[q];g=set(g)
        chosen=r["choices"]
        hits=[len({source,title(names[str(a)][1])}&g) for a in chosen]
        complete=[int(h==len(g)) for h in hits]
        ticks.append(r["seed"]);wins.append(complete);recs.append([h/len(g) for h in hits]);choices.append(chosen)
        cases[q]=[r["seed"],kind,len(g),hits,complete]
        for k in ("surface","direct","coordination"):groups[k+":"+str(bool(r[k]))].append(i)
        groups["type:"+kind].append(i);groups["support_n:"+str(len(g))].append(i)
    a=np.asarray(wins,dtype=np.int8);opts=np.asarray(choices)
    starts,ix=np.unique(ticks,return_inverse=True);n=np.bincount(ix)
    delta=np.stack([a[:,ARMS.index(l)]-a[:,ARMS.index(r)] for l,r in PAIRS],axis=1)
    by=np.stack([np.bincount(ix,weights=d) for d in delta.T],axis=1)
    draws=[];rng=np.random.default_rng(520117)
    for _ in range(100):
        samp=rng.integers(len(n),size=(100,len(n)));draws.append(by[samp].sum(1)/n[samp].sum(1)[:,None])
    limits=np.quantile(np.vstack(draws),[.025,.975],axis=0)
    contrasts={}
    for j,(l,r) in enumerate(PAIRS):
        x,y=map(ARMS.index,(l,r));d=delta[:,j]
        contrasts[l+" vs "+r]={"wins":int((d>0).sum()),"losses":int((d<0).sum()),"delta":float(d.mean()),
             "switched":int((opts[:,x]!=opts[:,y]).sum()),"ci95":limits[:,j].tolist()}
    out={"n":len(pred),"clusters":len(starts),"complete":dict(zip(ARMS,a.sum(0).tolist())),
         "recall":dict(zip(ARMS,np.mean(recs,axis=0).tolist())),"contrasts":contrasts,
         "strata":{k:{"n":len(v),"hits":dict(zip(ARMS,a[v].sum(0).tolist()))} for k,v in groups.items()}}
    return out,cases

def main():
    seal=read(HERE/"prediction-seal.json")
    for k,v in seal["local"].items():assert hashfile(HERE/k)==v
    largest=read(HERE/"predictions.json.gz");prior,oldnames,oldlabels=retrospective()
    assert set(largest).isdisjoint(prior)
    assert {r["seed"] for r in largest.values()}.isdisjoint(r["seed"] for r in prior.values())
    authors=gold_from_authors(read(S/"questions.json.gz"));names=read(HERE/"chosen-titles.json.gz")
    original,_=grade(prior,oldnames,oldlabels)
    out,cases=grade(largest,names,authors)
    save(HERE/"graded-rows.json.gz",cases)
    save(HERE/"results.json",{"independent_12000":out,"retrospective_2400":original,"arms":ARMS})
    print(out["complete"]);print(out["contrasts"]);print("Retrospective:",original["complete"])

if __name__=="__main__":main()

