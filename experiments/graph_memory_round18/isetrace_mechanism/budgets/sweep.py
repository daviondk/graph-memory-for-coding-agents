"""Replay unchanged stored BM25 rankings at all paper budgets using the original budget function and scorer."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[1]/"isetrace_official"
sys.path.insert(0,str(SOURCE))
from discover import pilot
from graph_memory.evaluation.span_suite import CONTEXT_TOKEN_BUDGETS, normalized_budget_auc
from score import streamgz

BUDGETS=CONTEXT_TOKEN_BUDGETS
ARMS=("flat.prefix","provenance.prefix","provenance.skip","provenance.value","provenance.related")


def load(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix==".gz" else data)


def save(name,obj):
    data=json.dumps(obj,separators=(",",":"),ensure_ascii=False).encode()
    (ROOT/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)


def check(hash_map,root):
    for k,v in hash_map.items():
        assert pilot.sha(root/k)==v,k


def inputs():
    local=["PROTOCOL_RU.md","sweep.py"]
    return {"local":{k:pilot.sha(ROOT/k) for k in local},
            "inputs":{k:pilot.sha(SOURCE/k) for k in ["forecast-lock.json","placebo-event-metadata.json.gz"]}}


def predict():
    assert inputs()==load(ROOT/"design.json")
    events=load(SOURCE/"placebo-event-metadata.json.gz")
    forecasts=load(SOURCE/"forecast-lock.json")["forecasts"]
    check(forecasts,SOURCE)
    seals={}
    for s,f in enumerate(sorted(forecasts)):
        out={}
        for rec in streamgz(SOURCE/f):
            tid=rec["trajectory_id"]
            for q,views in rec["queries"].items():
                policies={}
                for view,v in views.items():
                    ranked=[SimpleNamespace(node_id=n["node_id"],score=n["score"],token_count=n["token_count"]) for n in v["ranked"]]
                    indices={n.node_id:j for j,n in enumerate(ranked)}
                    meta={}
                    if view=="provenance":
                        for n in v["ranked"]:
                            cid,role,_=events[tid][n["source_spans"][0]["event_id"]]
                            meta[n["node_id"]]=dict(call_id=str(cid) if cid>=0 else None,
                                                    node_kind="content.tool_argument" if role=="a" else "content.tool_output")
                    for arm in ARMS:
                        kind,policy=arm.split(".")
                        if kind!=view:
                            continue
                        path=[]
                        for b in BUDGETS:
                            kept=pilot.pack(ranked,meta,b,policy)
                            nodeids=[k.node_id for k in kept]
                            if b==2048:
                                assert nodeids==v["arms"][policy],(q,arm)
                            path.append([indices[key] for key in nodeids])
                        policies[arm]=path
                out[q]={"t":tid,"arms":policies}
        name=f"choices-{s}.json.gz"
        save(name,out)
        seals[name]=pilot.sha(ROOT/name)
    save("seal.json",{"design":pilot.sha(ROOT/"design.json"),"predictions":seals})


def score():
    seal=load(ROOT/"seal.json")
    assert seal["design"]==pilot.sha(ROOT/"design.json")
    check(seal["predictions"],ROOT)
    labels=load(SOURCE/"gold-spans.json.gz")
    reference={(x["q"],x["view"]+"."+x["arm"]):x for x in load(SOURCE/"outcomes.json.gz")}
    rows=[]
    for shard in range(8):
        selected=load(ROOT/f"choices-{shard}.json.gz")
        for rec in streamgz(SOURCE/f"forecasts-shard-{shard}.jsonl.gz"):
            for q,views in rec["queries"].items():
                gold=[pilot.SourceSpan.model_validate(v) for v in labels[q]]
                source={k:[pilot.RankedNodeRecord.model_validate(n) for n in v["ranked"]] for k,v in views.items()}
                assert selected[q]["t"]==rec["trajectory_id"]
                for arm,paths in selected[q]["arms"].items():
                    ranking=source[arm.split(".")[0]]
                    fs={};cov={};used=[]
                    for b,ix in zip(BUDGETS,paths,strict=True):
                        keep=[ranking[i] for i in ix]
                        count=sum(n.token_count for n in keep)
                        assert len(keep)==len(set(ix)) and count<=b
                        met=pilot.span_metrics_under_token_budget(keep,gold,b)
                        fs[b]=int(met.full_support)
                        cov[b]=met.coverage
                        used.append(count)
                        if b==2048:
                            ref=reference[q,arm]
                            assert (fs[b],cov[b],count)==(ref["full_support"],ref["coverage"],ref["tokens"])
                    rows.append(dict(q=q,t=rec["trajectory_id"],arm=arm,fs=list(fs.values()),cov=list(cov.values()),
                                     used=used,fs_auc=normalized_budget_auc(fs),cov_auc=normalized_budget_auc(cov)))
    assert len(rows)==10000
    save("outcomes.json.gz",rows)
    groups={a:{r["q"]:r for r in rows if r["arm"]==a} for a in ARMS}
    aggregate={}
    for a,items in groups.items():
        assert len(items)==2000
        aggregate[a]={k:np.mean([r[k] for r in items.values()],axis=0).tolist() for k in ("fs","cov","used","fs_auc","cov_auc")}
    trajectories=sorted({r["t"] for r in rows})
    tindex={t:i for i,t in enumerate(trajectories)}
    diffs=np.zeros((len(trajectories),3))
    for q,r in groups["provenance.related"].items():
        v=groups["provenance.value"][q]
        j=tindex[r["t"]]
        diffs[j]+=(r["fs_auc"]-v["fs_auc"],r["cov_auc"]-v["cov_auc"],1)
    rng=np.random.default_rng(13)
    samples=[]
    for _ in range(100):
        counts=diffs[rng.integers(len(diffs),size=(100,len(diffs)))].sum(axis=1)
        samples.append(counts[:,:2]/counts[:,2,None])
    ci=np.quantile(np.concatenate(samples),[.025,.975],axis=0).tolist()
    save("summary.json",dict(budgets=list(BUDGETS),means=aggregate,ci_FSandCoverage_AUC=ci,n=len(groups[ARMS[0]])))
    print(json.dumps(aggregate),ci,flush=True)


if __name__=="__main__":
    stage=sys.argv[1]
    if stage=="lock":
        assert not (ROOT/"design.json").exists()
        save("design.json",inputs())
    elif stage=="predict":
        predict()
    else:
        score()

