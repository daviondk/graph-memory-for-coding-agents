"""Native and independent character-level evaluation after the sealed forecasts."""
from collections import defaultdict
from dataclasses import asdict
from statistics import mean
import sys

import numpy as np
from pack import ROOT,WORK,R19,OFF,load,sha,put,merge,includes,CAP
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
sys.path.insert(0,str(WORK/"graph_memory_round17/isetrace"))
from verify_records import metrics as independent

ARMS=("skip","U","W","F","W0","F0")
CONTRASTS=(("F","skip"),("W","skip"),("F","W"),("F","F0"),("W","W0"),("F0","skip"),("U","skip"))


def signature(rows):
    by=defaultdict(list)
    for e,p,a,b,c in rows:
        assert 0<=a<b and c>0
        by[e,p].append((a,b))
    return {k:merge(v) for k,v in by.items()}


def calc(rows,labels):
    nodes=[dict(node_id="quote-"+str(i),score=0.,token_count=cost,source_spans=[dict(event_id=e,json_pointer=p,char_start=a,char_end=b)])
           for i,(e,p,a,b,cost) in enumerate(rows)]
    tok=sum(n["token_count"] for n in nodes);assert 0<tok<=CAP
    api=asdict(span_metrics_under_token_budget(tuple(RankedNodeRecord.model_validate(x) for x in nodes),
             tuple(SourceSpan.model_validate(s) for s in labels),CAP))
    manual=independent(labels,nodes)
    assert all(abs(api[f]-v)<1e-12 for f,v in zip(("coverage","density","full_support"),manual))
    independent_f1=2*manual[0]*manual[1]/(manual[0]+manual[1]) if manual[0]+manual[1] else 0.
    assert abs(api["f1"]-independent_f1)<1e-12
    sig=signature(rows)
    return {**api,"tokens":tok,"parts":len(rows),"events":len(sig),"chars":sum(b-a for xs in sig.values() for a,b in xs)}


def paired(rows,a,b):
    group=sorted({r["t"] for r in rows});index={v:i for i,v in enumerate(group)}
    cols=["full_support","coverage","density","f1","tokens","chars","events"]
    d=np.array([[r["a"][a][c]-r["a"][b][c] for c in cols] for r in rows])
    idx=np.array([index[r["t"]] for r in rows]);counts=np.bincount(idx)
    sums=np.stack([np.bincount(idx,weights=d[:,i]) for i in range(len(cols))],axis=1)
    rng=np.random.default_rng(20);samples=[]
    for _ in range(100):
        choices=rng.integers(len(group),size=(100,len(group)))
        samples.append(sums[choices].sum(axis=1)/counts[choices].sum(axis=1)[:,None])
    ci=np.percentile(np.concatenate(samples),[2.5,97.5],axis=0).T
    return dict(n=len(rows),tr=len(group),win=int((d[:,0]>0).sum()),lose=int((d[:,0]<0).sum()),
        change={c:dict(mean=d[:,i].mean(),ci=ci[i].tolist()) for i,c in enumerate(cols)})


def main(method):
    seal=load(ROOT/f"{method}-forecast-seal.json");extra=load(ROOT/f"{method}-duplicate-seal.json")
    for s in (seal,extra):
        assert all(sha(ROOT/m["file"])==m["sha"] for m in s["shards"])
    gold=load(OFF/"gold-spans.json.gz");records=[]
    for i in range(8):
        raw=load(ROOT/f"{method}-pred-{i}.json.gz")
        dup={r["q"]:r for r in load(ROOT/f"{method}-dup-{i}.json.gz")}
        for rec in raw:
            q=rec["q"];assert dup[q]["t"]==rec["t"]
            combined={**rec["arms"],**dup[q]["arms"]}
            maps={arm:signature(x) for arm,x in combined.items()}
            for left,right in [("skip","U"),("U","W"),("W","F"),("skip","W0"),("W0","F0")]:
                assert includes(maps[left],maps[right])
            assert maps["skip"]==maps["U"]
            a={name:calc(rs,gold[q]) for name,rs in combined.items()}
            records.append(dict(q=q,t=rec["t"],a=a,info={**rec["info"],"no_merge_infeasible":dup[q]["infeasible"]}))
    assert len(records)==2000==len(gold) and {r["q"] for r in records}==set(gold)
    if method=="dense":
        base={r["q"]:r for r in load(R19/"trained_rank/outcomes.json.gz") if r["arm"]=="skip"}
        for row in records:
            assert all(abs(row["a"]["skip"][k]-base[row["q"]][k])<1e-12 for k in ("tokens","coverage","density","f1","full_support"))
    stats={a:{k:mean(r["a"][a][k] for r in records) for k in records[0]["a"][a]}
            |dict(count=int(sum(r["a"][a]["full_support"] for r in records))) for a in ARMS}
    contrasts={a+"-"+b:paired(records,a,b) for a,b in CONTRASTS}
    strata={}
    for label,items in [("skip-overlap",[r for r in records if r["info"]["overlap_char"]>0]),
                        ("skip-nooverlap",[r for r in records if not r["info"]["overlap_char"]])]:
        if items:
            strata[label]={"n":len(items),"F-skip":paired(items,"F","skip"),"F-F0":paired(items,"F","F0")}
    saving=[r["info"]["native_actual"]-r["info"]["union_seed"] for r in records]
    nominal=[r["a"]["skip"]["tokens"]-r["a"]["U"]["tokens"] for r in records]
    incidence=dict(chars_added=sum(r["a"]["F"]["chars"]>r["a"]["skip"]["chars"] for r in records),
        event_added=sum(r["a"]["F"]["events"]>r["a"]["skip"]["events"] for r in records),
        whole_added=sum(r["info"]["whole_add"]>0 for r in records),window_added=sum(r["info"]["window_add"]>0 for r in records),
        intrinsic_overlap=sum(r["info"]["overlap_char"]>0 for r in records),render_overflow=sum(r["info"]["native_actual"]>CAP for r in records),
        rerender_diff=sum(r["info"]["native_actual"]!=r["a"]["skip"]["tokens"] for r in records),
        mean_true_saved=mean(saving),true_saved_quantiles=np.percentile(saving,[0,25,50,75,95,100]).tolist(),
        mean_native_minus_U=mean(nominal),mean_raw_render=mean(r["info"]["native_actual"] for r in records),
        base_fallback=sum(r["info"]["fallback"] for r in records),base_infeasible=sum(r["info"]["infeasible"] for r in records),
        dup_infeasible=sum(r["info"]["no_merge_infeasible"] for r in records))
    put(ROOT/f"{method}-outcomes.json.gz",records)
    result=dict(stats=stats,paired=contrasts,strata=strata,incidence=incidence,
        gold_sha256=sha(OFF/"gold-spans.json.gz"),forecasts=sha(ROOT/f"{method}-forecast-seal.json"),
        duplicates=sha(ROOT/f"{method}-duplicate-seal.json"))
    put(ROOT/f"{method}-results.json",result)
    print(method,{k:x["count"] for k,x in stats.items()},incidence,
          {k:(v["win"],v["lose"],v["change"]["full_support"]) for k,v in contrasts.items()},flush=True)


if __name__=="__main__":main(sys.argv[1])
