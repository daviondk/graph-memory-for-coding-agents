"""Infer once on unrevealed exact ranks, then score the 80 withheld parent-development queries separately."""
import collections
import dataclasses
import os
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import study as s
import score
sys.path.insert(0,str(HERE.parent/"mechanism"))
import ablate
import numpy as np
PRIVATE=Path(os.environ.get("TYPED_DATA","D:/CodexResearch/x20-typed-reader-private"))
OLD=s.HERE.parent.parent/"graph_memory_round19/write_transfer"

def ranks(path,expected_sha):
    assert s.sha(path)==expected_sha
    rows=s.read(path)
    if isinstance(rows,dict):
        assert "rows" in rows;rows=rows["rows"]
    plan=s.read(HERE/"source-plan.json")
    assert len(rows)==80 and {r["q"]:r["t"] for r in rows}==plan["queries"]
    for r in rows:
        assert len(r["rr"])==len({n["node_id"] for n in r["rr"]}) and all(n["token_count"]>0 for n in r["rr"])
        assert all(x["score"]>=y["score"]-1e-12 for x,y in zip(r["rr"],r["rr"][1:]))
    return rows,plan

def infer(path,h):
    rows,plan=ranks(path,h)
    ix=s.graph_index()
    for t,x in plan["records"].items():
        if x["native"]:assert ix[t][1]==x["sha"]
        else:ix[t]=(PRIVATE/f"{t}.json.gz",x["sha"])
    models={}
    wdig={}
    for name,src in (("dev",s.HERE),("train",s.HERE/"train_bm25")):
        f=src/"weights.json"
        assert s.sha(f)==s.read(src/"fit-seal.json")["weights"]
        af=s.HERE/"mechanism"/f"weights-{name}.json"
        assert s.sha(af)==s.read(s.HERE/"mechanism"/f"fit-{name}.json")["weights"]
        models[name]=(s.read(f),s.read(af));wdig[name]=[s.sha(f),s.sha(af)]
    by=collections.defaultdict(list)
    for r in rows:by[r["t"]].append(r)
    out=[]
    for t,rs in sorted(by.items()):
        gr=s.project(t,ix)
        for r in rs:
            rr=r["rr"]; cost=[n["token_count"] for n in rr]
            base=s.project_rows(rr,gr);extra=ablate.design(rr,gr)
            sel={"dense":{p:s.pack(np.arange(len(rr)),cost,p=="skip") for p in ("prefix","skip")}}
            for stage,(f,a) in models.items():
                for arm,model in (f|a).items():
                    v=(base|extra)[arm]
                    order=np.argsort(-(v@np.asarray(model["w"])+model["bias"]),kind="stable")
                    sel[stage+"/"+arm]={p:s.pack(order,cost,p=="skip") for p in ("prefix","skip")}
            out.append(dict(q=r["q"],t=t,selection=sel))
    pred=HERE/"forecasts.json.gz";s.put(pred,out)
    s.put(HERE/"forecast-seal.json",dict(raw_sha=h,raw_name=path.name,input=s.sha(HERE/"source-plan.json"),weights=wdig,
            predictions=s.sha(pred),protocol=s.sha(HERE/"PROTOCOL_RU.md"),code=s.sha(Path(__file__)),q=len(out),t=len(by)))
    print("heldout forecasts sealed",len(out),len(by),flush=True)

def differences(rows,variant,base="dense"):
    left={r["q"]:r for r in rows if r["arm"]==variant}
    right={r["q"]:r for r in rows if r["arm"]==base}
    assert set(left)==set(right)
    gs=collections.defaultdict(list)
    for q in sorted(left):
        gs[left[q]["t"]].append([left[q][f]-right[q][f] for f in ("full_support","coverage")])
    d=np.array([val for vs in gs.values() for val in vs])
    arr=np.array([np.sum(v,axis=0) for _,v in sorted(gs.items())]);den=np.array([len(v) for _,v in sorted(gs.items())])
    rng=np.random.default_rng(13);sim=[]
    for _ in range(40):
        idx=rng.integers(0,len(arr),size=(250,len(arr)))
        sim.extend(arr[idx].sum(axis=1)/den[idx].sum(axis=1)[:,None])
    ci=np.quantile(sim,[.025,.975],axis=0)
    return {f:dict(delta=float(d[:,k].mean()),ci=ci[:,k].tolist(),win=int(np.sum(d[:,k]>1e-13)),loss=int(np.sum(d[:,k]< -1e-13)),
                ties=int(np.sum(abs(d[:,k])<=1e-13)),q=len(d),clusters=len(gs)) for k,f in enumerate(("full_support","coverage"))}

def report(path,h):
    seal=s.read(HERE/"forecast-seal.json")
    assert seal["raw_sha"]==h and seal["predictions"]==s.sha(HERE/"forecasts.json.gz")
    rows,plan=ranks(path,h);many={r["q"]:r for r in rows}
    truth=s.read(OLD/"gold-spans.json.gz")
    out=[]
    for rec in s.read(HERE/"forecasts.json.gz"):
        q=rec["q"];rr=many[q]["rr"];gs=tuple(score.SourceSpan.model_validate(v) for v in truth[q])
        nodes=[score.RankedNodeRecord.model_validate(n) for n in rr]
        for a,pol in rec["selection"].items():
            for p,ids in pol.items():
                selected=tuple(nodes[i] for i in ids);used=sum(n.token_count for n in selected)
                assert used<=2048 and len(ids)==len(set(ids))
                m=score.span_metrics_under_token_budget(selected,gs,2048)
                alt=score.ind.metrics(truth[q],[rr[i] for i in ids])
                assert all(abs(v-getattr(m,f))<1e-12 for v,f in zip(alt,("coverage","density","full_support"),strict=True))
                out.append(dict(q=q,t=rec["t"],arm=a,policy=p,tokens=used,nodes=len(ids),**dataclasses.asdict(m)))
    s.put(HERE/"outcomes.json.gz",out)
    agg={}
    novel=set(plan["novel_trajectories"])
    for nm,cond in (("all",lambda r:True),("novel",lambda r:r["t"] in novel),("shared",lambda r:r["t"] not in novel)):
        for pol in ("prefix","skip"):
            z=[r for r in out if cond(r) and r["policy"]==pol]
            means={};pairs={}
            for a in sorted({r["arm"] for r in z}):
                v=[r for r in z if r["arm"]==a]
                means[a]={f:float(np.mean([r[f] for r in v])) for f in score.FIELDS}|{"hits":sum(int(r["full_support"]) for r in v),"n":len(v)}
                if a!="dense":pairs[a+"-dense"]=differences(z,a)
            for stage in ("train","dev"):
                for a,b in (("typed","shuffled"),("typed","degrees"),("typed","role_degrees"),("role_degrees","role"),("role_degrees","degrees")):
                    pairs[stage+"/"+a+"-"+b]=differences(z,stage+"/"+a,stage+"/"+b)
            agg[nm+"/"+pol]=dict(means=means,pairs=pairs)
    s.put(HERE/"results.json",agg)
    print([(k,v["means"]["dense"]["hits"],v["means"]["train/role_degrees"]["hits"],v["pairs"]["train/role_degrees-dense"]["full_support"]) for k,v in agg.items() if k.endswith("/prefix")],flush=True)
if __name__=="__main__":
    {"infer":infer,"score":report}[sys.argv[1]](Path(sys.argv[2]),sys.argv[3])
