"""Geometry only on a locked hash-sampled independent panel of training trajectories."""
from geometry import *
def run():
    base=W/"graph_memory_round19/write_learned"
    epath=base/"train-evidence.json.gz";previous=load(epath)
    plan=load(base/"plan.json");assert set(previous)==set(plan["selection"])
    oldtrain={r["t"] for r in feature("train")}
    source={};prod={}
    for t,v in previous.items():
        if t in oldtrain:continue
        path=old.PROJ/"train"/(t+".json.gz");assert sha(path)==v["base_projection_sha"]==plan["train_projection_sha"][t]
        p=load(path);assert p["digest"]==v["raw_record"]
        index={a["item_id"]:i for i,a in enumerate(p["pool"])};spans=[z["source_spans"] for z in p["pool"]]
        for rec in p["qs"]:
            q=rec["q"];atoms=atomize(spans,v["q"][q]);gs=buckets(atoms)
            pos={i for *_,arr in atoms for i in arr};assert pos=={index[n] for n in rec["positive"]}
            prod[q]=dict(t=t,atoms=len(atoms),positive=len(pos),any_multi=any(len(g)>1 for *_,g in atoms),
                minimal_multi=any(len(g)>1 for g in gs),nonessential=bool(pos-{g[0] for g in gs if len(g)==1}),empty=any(not g for g in gs))
    save(D/"supplement-train-geometry.json.gz",prod)
    save(D/"supplement-train-summary.json",dict(n=len(prod),t=len({r["t"] for r in prod.values()}),counts={k:sum(v[k] for v in prod.values()) for k in ["any_multi","minimal_multi","nonessential","empty"]},
        upstream_gold=sha(epath),sampling_plan=sha(base/"plan.json"),rows=sha(D/"supplement-train-geometry.json.gz"),description="geometry only; trajectories disjoint from all 196 correction-train questions, selected by original 256-trajectory hash panel"))
    print(load(D/"supplement-train-summary.json"))
if __name__=="__main__":run()