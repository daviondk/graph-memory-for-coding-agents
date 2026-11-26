"""Paired evidence-availability audit. Run only after the forecast seal exists."""
from collections import Counter, defaultdict
from pathlib import Path
import unicodedata
import json
import numpy as np
from corpus import ROOT, WORK, read, save, hashfile
from seal import ARMS

def canon(t):
    return unicodedata.normalize("NFC"," ".join(t.replace("_"," ").split()))

def extract_labels(src):
    import pyarrow.parquet as pq
    assert hashfile(src)==read(ROOT/"source.json")["dev"]
    labels={}
    for batch in pq.ParquetFile(src).iter_batches(columns=["_id","type","supporting_facts"]):
        for row in batch.to_pylist():
            facts=row["supporting_facts"]
            if isinstance(facts,str): facts=json.loads(facts)
            if isinstance(facts,dict): titles=facts["title"]
            else: titles=[item[0] if isinstance(item,list) else item["title"] for item in facts]
            assert titles and all(isinstance(t,str) and t for t in titles)
            labels[row["_id"]]=[row["type"],sorted(set(map(canon,titles)))]
    want={t for v in labels.values() for t in v[1]}
    covered=set()
    with (WORK/"titles.txt").open(encoding="utf8") as f:
        for line in f:
            name=canon(line.rstrip("\n").split("\t",1)[1])
            if name in want:covered.add(name)
    save(ROOT/"support.json.gz",labels)
    save(ROOT/"directory-coverage.json",dict(gold_titles=len(want),absent=sorted(want-covered)))

def grade():
    seal=read(ROOT/"prediction-seal.json")
    assert all(hashfile(ROOT/file)==digest for file,digest in seal["files"].items())
    rows=read(ROOT/"predictions.json.gz"); names=read(ROOT/"chosen-titles.json.gz")
    annotations=read(ROOT/"support.json.gz")
    coverage=read(ROOT/"directory-coverage.json");absent=set(coverage["absent"])
    assert set(annotations)==set(rows) and len(rows)==seal["n"] and ARMS==seal["arms"]
    cluster=[]; values=[];recalls=[];counts=[];mechanism=Counter();types=defaultdict(list)
    question_hits=Counter();size_groups=Counter();route_groups=defaultdict(list)
    selected=read(ROOT/"anchors.json.gz");example={}
    text_i,href_i=map(ARMS.index,("text","href"))
    for q in sorted(rows):
        seed,rawseed,choices,pool,flags=rows[q];counts.append(pool);cluster.append(seed)
        seedtitle=canon(names[str(seed)][1]);rawtitle=canon(names[str(rawseed)][1])
        targets=[canon(names[str(c)][1]) for c in choices]
        category,gold=annotations[q];gold=set(gold);remaining=gold-{seedtitle}
        hits=[len(gold&{seedtitle,t}) for t in targets]
        full=[int(hit==len(gold)) for hit in hits]
        idx=len(values);values.append(full);recalls.append([x/len(gold) for x in hits])
        types[category].append(idx);size_groups[len(gold)]+=1;types["n_support="+str(len(gold))].append(idx)
        question_hits.update({"common_first_hit":seedtitle in gold, "ordinary_bm25_first_hit":rawtitle in gold,
                              "one_remaining":len(remaining)==1, "all_titles_in_directory":not (gold&absent)})
        if len(remaining)==1 and not remaining&absent:route_groups["one_remaining_in_directory"].append(idx)
        if choices[text_i]!=choices[href_i]:route_groups["disagree"].append(idx)
        if pool[0]==0:route_groups["no_second_whole_title_in_question"].append(idx)
        if flags[0] and not flags[1]:route_groups["href_title_absent_in_prefix"].append(idx)
        label="win" if full[href_i]>full[text_i] else "loss" if full[href_i]<full[text_i] else "tie"
        if label!="tie":
            witness=("fallback" if not flags[0] else "literal_title_somewhere" if flags[1] else "target_absent")
            mechanism[label+":"+witness]+=1
            if label=="win" and q in selected and "alias_win" not in example:
                example["alias_win"]={"id":q,**selected[q],"gold":sorted(gold),"text_prediction":targets[text_i]}
    a=np.array(values,dtype=np.int16);r=np.array(recalls);pool=np.array(counts)
    group,ix=np.unique(cluster,return_inverse=True)
    denom=np.bincount(ix);diff=a[:,href_i]-a[:,text_i]
    d=np.bincount(ix,weights=diff)
    rng=np.random.default_rng(520117);draws=[]
    for _ in range(100):
        idx=rng.integers(len(group),size=(100,len(group)))
        draws.extend(d[idx].sum(axis=1)/denom[idx].sum(axis=1))
    def summary(sub):
        return dict(n=len(sub),complete=dict(zip(ARMS,a[sub].sum(axis=0).tolist())))
    return dict(n=len(a),clusters=len(group),arms=ARMS,complete=dict(zip(ARMS,a.sum(axis=0).tolist())),
                mean_support_recall=dict(zip(ARMS,r.mean(axis=0).tolist())),first=dict(question_hits),support_sizes=dict(size_groups),
                primary=dict(delta=float(diff.mean()),interval=np.quantile(draws,[.025,.975]).tolist(),
                    wins=int((diff>0).sum()),losses=int((diff<0).sum()),n_bootstrap=len(draws)),
                mechanisms=dict(mechanism),examples=example,directory=coverage["gold_titles"],absent=len(absent),
                pools=dict(columns=["question","literal","href","intersection"],mean=pool.mean(0).tolist(),median=np.median(pool,axis=0).tolist(),
                           p90=np.quantile(pool,.9,axis=0).tolist(),nonempty=(pool>0).sum(axis=0).tolist()),
                strata={k:summary(v) for k,v in (types|route_groups).items()})

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--extract",action="store_true");a=p.parse_args()
    seal=read(ROOT/"prediction-seal.json")
    assert all(hashfile(ROOT/file)==v for file,v in seal["files"].items())
    if a.extract:extract_labels(Path("D:/CodexResearch/x20-r32-2wiki/dev.parquet"))
    result=grade();save(ROOT/"results.json",result)
    print(result["primary"],result["complete"],flush=True)

