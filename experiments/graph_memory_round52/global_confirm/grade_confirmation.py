"""Grade sealed predictions against both the authors' original train.json and its parquet mirror."""
import json
import sys
import unicodedata
from collections import Counter,defaultdict
from zipfile import ZipFile
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from syntax import ARMS,choose
from panel import HERE,S,DEV,GT,GP,R50,PAR,read,save,hashfile

PAIRS=[("primary_href",x) for x in ("coord_cautious","primary_text","coord_question_only","coord_explicit","href_first","primary_free")]
PAIRS += [("learned_dev",x) for x in ("primary_href","coord_cautious","href_first")]
def title(t):
    return unicodedata.normalize("NFC"," ".join(t.replace("_"," ").split()))

def truth(keys,questions):
    # Independent agreement on all IDs, question texts, question types and complete support-title sets.
    source=read(HERE.parents[1]/"graph_memory_round50/qa_external/official-source.json")
    path=Path("D:/CodexResearch/x20-r50-qa-external/data_ids.zip")
    assert hashfile(path)==source["archive"] and hashfile(PAR)==read(HERE/"candidate-receipt.json")["train_sha256"]
    mirror={}
    for batch in pq.ParquetFile(PAR).iter_batches(columns=["_id","type","supporting_facts"]):
        for row in batch.to_pylist():
            k=row["_id"]
            if k in keys:
                s=row["supporting_facts"];s=json.loads(s) if isinstance(s,str) else s
                vals=s["title"] if isinstance(s,dict) else [v[0] if isinstance(v,list) else v["title"] for v in s]
                mirror[k]=[row["type"],sorted(set(map(title,vals)))]
    sys.path.insert(0,str(R50))
    from stream_json import iter_array
    gold={}
    with ZipFile(path) as z,z.open("data_ids/train.json") as f:
        for r in iter_array(f):
            k=r["_id"]
            if k in keys:
                assert r["question"]==questions[k]
                gold[k]=[r["type"],sorted({title(t) for t,i in r["supporting_facts"]})]
    assert len(gold)==len(keys) and gold==mirror
    save(HERE/"support.json.gz",gold)
    save(HERE/"truth-receipt.json",dict(official_archive=source["archive"],parquet=hashfile(PAR),
                                      ids=len(gold),match="exact on questions, types and unique canonical support titles",
                                      seal=hashfile(HERE/"prediction-seal.json")))
    return gold

def grade_rows(rows,names,gold):
    out={}
    for k,r in rows.items():
        kind,g=gold[k];g=set(g)
        src=title(names[str(r["seed"])][1])
        hit=[len(g&{src,title(names[str(d)][1])}) for d in r["choices"]]
        full=[int(h==len(g)) for h in hit]
        out[k]={"seed":r["seed"],"type":kind,"support_n":len(g),"hit":hit,"complete":full,
                "first_hit":int(src in g),"direct":int(r["direct_gate"][0]>=0),"coord":int(r["coordination"])}
    return out

def olddev(model):
    rows=read(GP/"predictions.json.gz");qa=read(DEV/"questions.json.gz")
    older=read(GT/"predictions.json.gz");oldorder=read(GT/"prediction-seal.json")["arms"]
    names=read(GP/"chosen-titles.json.gz")|read(GT/"chosen-titles.json.gz")
    labels=read(GT/"support.json.gz")
    forecasts={}
    for q,r in rows.items():
        seed=r["seed"];gate=r["gates"][1];v=older[q][2]
        pick=lambda n:v[oldorder.index(n)]
        choices,conj,_=choose(qa[q],names[str(seed)][1],gate,pick("question_bm25"),pick("href_first"),pick("text_first"),pick("free"),model)
        forecasts[q]={"seed":seed,"direct_gate":gate,"choices":choices,"coordination":conj}
    out=grade_rows(forecasts,names,labels)
    assert sum(r["complete"][0] for r in out.values())==4995 and sum(r["complete"][1] for r in out.values())==3655
    return out

def summary(rows, detailed=True):
    arr=np.array([r["complete"] for r in rows],dtype=np.int8)
    hits=np.array([r["hit"] for r in rows],dtype=np.float64)
    supports=np.array([r["support_n"] for r in rows])
    seeds,ix=np.unique([r["seed"] for r in rows],return_inverse=True)
    size=np.bincount(ix)
    diffs=np.stack([arr[:,ARMS.index(l)]-arr[:,ARMS.index(r)] for l,r in PAIRS],axis=1)
    by=np.stack([np.bincount(ix,weights=d) for d in diffs.T],axis=1)
    rng=np.random.default_rng(520117);boot=[]
    for _ in range(100):
        sel=rng.integers(len(seeds),size=(100,len(seeds)))
        boot.append(by[sel].sum(1)/size[sel].sum(1)[:,None])
    bounds=np.quantile(np.vstack(boot),[.025,.975],axis=0)
    contrast={}
    for j,(l,r) in enumerate(PAIRS):
        d=diffs[:,j]
        contrast[l+" vs "+r]=dict(delta=float(d.mean()),ci95=bounds[:,j].tolist(),wins=int((d>0).sum()),losses=int((d<0).sum()))
    out={"n":len(rows),"clusters":len(seeds),"first_hit":sum(r["first_hit"] for r in rows),
         "complete":dict(zip(ARMS,arr.sum(0).tolist())),"support_recall":dict(zip(ARMS,(hits/supports[:,None]).mean(0).tolist())),
         "contrasts":contrast}
    if detailed:
        strata=defaultdict(list)
        for i,row in enumerate(rows):
            for key in ("type","support_n","direct","coord"):strata[key+":"+str(row[key])].append(i)
        out["subsets"]={k:{"n":len(v),"hits":dict(zip(ARMS,arr[v].sum(0).tolist()))} for k,v in strata.items()}
    return out

def main():
    seal=read(HERE/"prediction-seal.json")
    for k,v in seal["local"].items():assert hashfile(HERE/k)==v
    pred=read(HERE/"predictions.json.gz")
    labels=truth(set(pred),read(S/"questions.json.gz"))
    conf=grade_rows(pred,read(HERE/"chosen-titles.json.gz"),labels)
    d=olddev(read(HERE/"dev-model.json"));assert set(conf).isdisjoint(d)
    assert {r["seed"] for r in conf.values()}.isdisjoint(r["seed"] for r in d.values())
    clean=set(read(HERE/"novelty.json")["ever_unseen_ids"])
    out={"arms":ARMS,"train_confirm":summary(list(conf.values())),"ever_unseen":summary([r for q,r in conf.items() if q in clean]),
         "development":summary(list(d.values()),False),"pooled":summary(list(d.values())+list(conf.values()),False)}
    save(HERE/"graded-rows.json.gz",conf);save(HERE/"results.json",out)
    print(out["train_confirm"]["complete"])
    print({k:v for k,v in out["train_confirm"]["contrasts"].items()})

if __name__=="__main__":main()

