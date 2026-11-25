"""Score the sealed candidate indices with the published span scorer."""
from collections import defaultdict
from predict_readout import ARMS, D, R20, ref, save
import numpy as np
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan


def paired(rows,arm,b):
    groups=defaultdict(list)
    for r in rows:
        a0,b0=r["arms"][arm],r["arms"][b]
        groups[r["t"]].append([a0[k]-b0[k] for k in ("fs","coverage","tokens")])
    vals=np.concatenate([np.array(rs) for rs in groups.values()])
    n=np.array([len(rs) for rs in groups.values()])
    x=np.array([np.sum(rs,axis=0) for rs in groups.values()]);rng=np.random.default_rng(21014);samples=[]
    for block in range(40):
        idx=rng.integers(0,len(n),size=(250,len(n)))
        samples.append(x[idx].sum(axis=1)/n[idx].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(samples),[.025,.975],axis=0)
    return dict(deltas={k:{"mean":float(vals[:,j].mean()),"ci":ci[:,j].tolist()} for j,k in enumerate(("fs","coverage","tokens"))},
                fs_wins=int((vals[:,0]>0).sum()),fs_losses=int((vals[:,0]<0).sum()),fs_ties=int((vals[:,0]==0).sum()),
                changed=sum(r["different"][arm+"/"+b] for r in rows))


def run():
    seal=ref.read(D/"readout-lock.json")
    assert seal["code"]==ref.sha(D/"predict_readout.py") and seal["protocol"]==ref.sha(D/"READOUT_PROTOCOL_RU.md")
    truth=ref.read(ref.OFF/"gold-spans.json.gz")
    reference={r["q"]:r for r in ref.read(R20/"typed_reader/outcomes.json.gz") if r["arm"]=="typed" and r["policy"]=="prefix"}
    observations=[]
    contrasts=(("exact","append"),("half","append"),("half","exact"),("append","shuffled"))
    for i in range(8):
        fp=D/f"readout-{i}.json.gz"
        assert ref.sha(fp)==seal["forecasts"][fp.name]
        source={r["q"]:r for r in ref.read(ref.TR/f"forecasts-main-{i}.json.gz")}
        for p in ref.read(fp):
            q=p["q"];rr=[RankedNodeRecord.model_validate(n) for n in source[q]["rr"]]
            gold=tuple(SourceSpan.model_validate(s) for s in truth[q]);arms={};memo={}
            for a,idx in p["picks"].items():
                key=tuple(idx)
                if key not in memo:
                    passage=tuple(rr[i] for i in idx);cost=sum(n.token_count for n in passage)
                    assert cost<=2048 and len(set(idx))==len(idx)
                    m=span_metrics_under_token_budget(passage,gold,2048)
                    memo[key]=dict(fs=int(m.full_support),coverage=m.coverage,density=m.density,tokens=cost)
                arms[a]=memo[key]
            assert arms["exact"]["fs"]==reference[q]["full_support"] and arms["exact"]["coverage"]==reference[q]["coverage"]
            changed={a+"/"+b:p["picks"][a]!=p["picks"][b] for a,b in contrasts}
            observations.append(dict(q=q,t=p["t"],pilot=p["pilot"],arms=arms,different=changed))
    assert len(observations)==2000 and {r["q"] for r in observations}==set(truth)
    save(D/"readout-outcomes.json.gz",observations)
    groups={}
    for name,subset in (("confirmatory_panel",[r for r in observations if not r["pilot"]]),("pilot",[r for r in observations if r["pilot"]]),("all",observations)):
        groups[name]={"n":len(subset),"trajectories":len({r["t"] for r in subset}),
            "summary":{a:{"hits":sum(r["arms"][a]["fs"] for r in subset),"coverage":float(np.mean([r["arms"][a]["coverage"] for r in subset]))}
                       for a in ARMS},"paired":{a+"/"+b:paired(subset,a,b) for a,b in contrasts}}
    diag=ref.read(D/"readout-graph-audit.json.gz")
    save(D/"readout-results.json",{"panels":groups,"graph":{k:sum(r[k] for r in diag) for k in ("extra","changed","exact")},
         "changed_trajectories":sum(bool(r["extra"]) for r in diag),"outcomes":ref.sha(D/"readout-outcomes.json.gz"),
         "lock":ref.sha(D/"readout-lock.json"),"code":ref.sha(D/"score_readout.py")})
    print(groups["confirmatory_panel"]["summary"],groups["confirmatory_panel"]["paired"]["exact/append"],flush=True)

if __name__=="__main__":run()
