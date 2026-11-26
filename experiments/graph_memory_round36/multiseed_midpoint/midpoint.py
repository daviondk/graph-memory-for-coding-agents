"""Frozen as-of graph readout, replicated on five dense encoder rankings."""
import hashlib
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

for key in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[key]="1"
import numpy as np
D=Path(__file__).resolve().parent
SRC=D.parent/"materialized_append"
sys.path.insert(0,str(SRC))
import materialize as m
l=m.l
SEEDS=(13,17,29,37,41)
ARMS=("E","M","L","E35")

def paths(seed, shard):
    base=m.W/f"graph_memory_round21/five_seed/seed-{seed}"
    return base/"calibration.json",base/f"picks-{shard}.json.gz",base/"forecast-seal.json"

def compute(sh):
    plan=m.load(D/"plan.json")
    raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl"
    assert m.sha(raw)==m.load(m.R34/"plan.json")["raw"][raw.name]
    canonical=l.ref.TR/f"forecasts-main-{sh}.json.gz"
    by=defaultdict(list)
    for r in m.load(canonical):by[r["t"]].append(r)
    original={q:arms for q,t,cut,arms in m.load(SRC/f"orders-{sh}.json.gz") if cut==50}
    graph,rank,_,patch,_=l.read_models()
    large=m.load(m.W/"graph_memory_round35/calibration_scale/models.json")["models"]["oof_3894"]
    ranks={13:rank}; dense={}
    for seed in SEEDS[1:]:
        cp,fp,sp=paths(seed,sh);receipt=m.load(sp)
        assert m.sha(cp)==receipt["rank_weights"] and m.sha(fp)==next(z["sha"] for z in receipt["receipts"] if z["file"]==fp.name)
        ranks[seed]=m.load(cp)["rank"];dense[seed]={r["q"]:r["dense"] for r in m.load(fp)}
    index=l.ref.graph_index();out=[]
    for line,row in l.env.pilot.stream(raw):
        t=row["session_id"]
        if t not in by:continue
        path,dig=index[t];assert m.sha(path)==dig
        rec=m.load(path);assert hashlib.sha256(line).hexdigest()==rec["raw_source"]
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(row),source_revision=l.env.pilot.RAW[1])
        ids,g=l.geometry(rec);first,groups=l.parent.lookup(tr,rec,ids,g);cut=l.parent.cuts_for(tr.events)[1]
        feed=l.FeedIndex();visible=set();historical=set()
        for i,event in enumerate(tr.events[:cut+1]):
            feed.consume(event)
            if event.event_type=="tool_output":visible.add(event.call_id)
            if event.event_type in ("tool_call","tool_output"):
                historical.update((a,b) for a,b in feed.support if a in visible and b in visible and a in groups and b in groups)
        idx=np.flatnonzero(first<=cut)
        _,base=l.parent.truncate(g,idx,feed,groups)
        _,middle=l.parent.truncate(g,idx,SimpleNamespace(support=historical,ever=feed.ever),groups)
        names=list(ids);nodes=[names[i] for i in idx];address={n:i for i,n in enumerate(nodes)};pri={}
        meta={r["node_id"]:r for r in by[t][0]["rr"]}
        for method,geom in [("E",base["exact"]),("M",middle["exact"]),("L",base["append"])]:
            fx,cost=l.features(nodes,geom,meta);pri[method]=l.score(graph,fx)
        n=len(nodes);ranks_visible=np.arange(1,n+1)
        xx=np.column_stack([-np.log(ranks_visible),1/ranks_visible,(n-ranks_visible)/max(1,n-1)])
        signals={seed:l.score(ranks[seed],xx) for seed in SEEDS}
        for r in by[t]:
            q=r["q"];pool=r["rr"];locations=np.array([address.get(v["node_id"],-1) for v in pool])
            selected={}
            for seed in SEEDS:
                dx=np.arange(len(pool)) if seed==13 else np.asarray(dense[seed][q])
                assert sorted(dx)==list(range(len(pool)))
                avail=dx[locations[dx]>=0];local=locations[avail];assert len(local)==n
                cost_rank=cost[local];role=fx[local,0]
                x=np.column_stack([np.log1p(ranks_visible),np.log1p(cost_rank),role,role*np.log1p(cost_rank)])
                choices={}
                small=l.correct(patch,x)
                for arm in ARMS:
                    extra=l.correct(large,x) if arm=="E35" else small
                    prior=pri["E" if arm=="E35" else arm]
                    score=signals[seed]+prior[local]+extra
                    order=np.argsort(-score,kind="stable")
                    choices[arm]=avail[l.prefix(order,cost_rank,2048)].tolist()
                if seed==13:assert all(choices[k]==original[q][k][2] for k in ("E","M","L"))
                selected[str(seed)]=choices
            out.append({"q":q,"t":t,"seeds":selected})
    assert set(original)=={r["q"] for r in out}
    f=D/f"predictions-{sh}.json.gz";m.put(f,out);return f.name,m.sha(f)

def evaluate():
    seal=m.load(D/"forecast-seal.json")
    gold=m.load(l.ref.OFF/"gold-spans.json.gz")
    past={r["q"]:r for r in m.load(SRC/"outcomes.json.gz") if r["cut"]==50}
    outcomes={}
    for sh in range(8):
        fp=D/f"predictions-{sh}.json.gz";assert m.sha(fp)==seal["files"][fp.name]
        pool={r["q"]:[l.RankedNodeRecord.model_validate(k) for k in r["rr"]] for r in m.load(l.ref.TR/f"forecasts-main-{sh}.json.gz")}
        for item in m.load(fp):
            q=item["q"];t=item["t"];assert past[q]["t"]==t
            gs=tuple(l.SourceSpan.model_validate(x) for x in gold[q]);methods={}
            memo={}
            for seed,arms in item["seeds"].items():
                methods[seed]={}
                for k,ids in arms.items():
                    ix=tuple(ids)
                    if ix not in memo:
                        seq=tuple(pool[q][i] for i in ix);assert sum(r.token_count for r in seq)<=2048
                        v=l.span_metrics_under_token_budget(seq,gs,2048);memo[ix]=[int(v.full_support),v.coverage]
                    methods[seed][k]=memo[ix]
                    if seed=="13" and k!="E35":assert memo[ix]==past[q]["arms"][k][:2]
            outcomes[q]=dict(t=t,eligible=past[q]["eligible"],pilot=past[q]["pilot"],seeds=methods)
    assert len(outcomes)==2000
    m.put(D/"outcomes.json.gz",outcomes)
    keep=[r for r in outcomes.values() if r["eligible"] and not r["pilot"]]
    ts,ids=np.unique([r["t"] for r in keep],return_inverse=True);nn=np.bincount(ids)
    assert len(keep)==901 and len(ts)==657
    arr=np.array([[[r["seeds"][str(s)][k] for k in ARMS] for s in SEEDS] for r in keep])
    comparisons=[("M","L"),("E","L"),("E","M"),("E35","E")]
    delta=np.stack([arr[:,:,ARMS.index(a)]-arr[:,:,ARMS.index(b)] for a,b in comparisons],axis=2)
    grouped=np.zeros((len(ts),*delta.shape[1:]));np.add.at(grouped,ids,delta)
    panel={}
    for key,indices in [("transfer4",[1,2,3,4]),("all5",list(range(5)))]:
        n=len(indices);stats=grouped[:,indices];fixed=[];cross=[];rng=np.random.default_rng(360726)
        for _ in range(100):
            tr=rng.integers(len(ts),size=(100,len(ts)))
            w=np.stack([np.bincount(a,minlength=len(ts)) for a in tr])
            vals=(w@stats.reshape(len(ts),-1)).reshape(100,n,4,2)/(w@nn)[:,None,None,None]
            fixed.extend(vals.mean(1));se=rng.integers(n,size=(100,n));cross.extend(vals[np.arange(100)[:,None],se].mean(1))
        ci=lambda v:(100*np.quantile(v,[.025,.975],axis=0)).tolist()
        panel[key]=dict(means=(100*arr[:,indices].mean((0,1))).tolist(),diff=(100*delta[:,indices].mean((0,1))).tolist(),fixed_ci=ci(fixed),cross_ci=ci(cross))
    m.put(D/"results.json",dict(n=len(keep),clusters=len(ts),arms=ARMS,metrics=["FS2048","C2048"],contrasts=comparisons,panels=panel,
              successes_by_seed=arr[:,:,:,0].sum(0).astype(int).tolist(),outcomes=m.sha(D/"outcomes.json.gz"),seal=m.sha(D/"forecast-seal.json")))

if __name__=="__main__":
    m.put(D/"plan.json",dict(protocol=m.sha(D/"PROTOCOL_RU.md"),source=m.sha(SRC/"manifest.json"),scale=m.sha(m.W/"graph_memory_round35/calibration_scale/manifest.json"),code=m.sha(Path(__file__)),
                           seeds=SEEDS,arms=ARMS))
    with ProcessPoolExecutor(2) as pool:parts=dict(pool.map(compute,range(8)))
    m.put(D/"forecast-seal.json",dict(plan=m.sha(D/"plan.json"),files=parts))
    evaluate()

