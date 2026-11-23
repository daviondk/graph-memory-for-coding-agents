"""Post-hoc difference-in-differences in the same 2,000 questions across two matched rankings."""
from collections import Counter,defaultdict
from pathlib import Path
import sys
import numpy as np
from tail import D,E5,FT,OFF,load,put,pilot
def run():
    truth=load(OFF/"gold-spans.json.gz");both={};hashes={}
    official={q:tuple(pilot.SourceSpan.model_validate(x) for x in s) for q,s in truth.items()}
    for label,src in (("frozen",E5),("trained",FT)):
        seal=load(src/"forecast-seal.json");hashes[label]=pilot.sha(src/"forecast-seal.json")
        old=load(label+"-outcomes.json.gz");rows={}
        for i in range(8):
            f=f"forecasts-main-{i}.json.gz";assert pilot.sha(src/f)==seal["forecasts"][f]
            for r in load(src/f):
                q=r["q"];assert q not in rows
                pool={n["node_id"]:pilot.RankedNodeRecord.model_validate(n) for n in r["rr"]}
                pair={}
                for arm in ("related","skip"):
                    selected=tuple(pool[k] for k in r["arms"][arm]);cost=sum(n.token_count for n in selected);assert cost<=2048
                    result=pilot.span_metrics_under_token_budget(selected,official[q],2048)
                    pair[arm]=int(result.full_support)
                    if arm=="related":assert pair[arm]==old[q]["related"]["full_support"]
                rows[q]={"t":r["t"],**pair}
        both[label]=rows
    assert set(both["frozen"])==set(both["trained"])==set(truth) and len(truth)==2000
    clusters=defaultdict(list);observations={};model={}
    for label,rows in both.items():
        diffs=[r["related"]-r["skip"] for r in rows.values()]
        model[label]={"skip":sum(r["skip"] for r in rows.values()),"related":sum(r["related"] for r in rows.values()),"wins":diffs.count(1),"losses":diffs.count(-1),"delta":sum(diffs)/len(diffs)}
    for q in sorted(truth):
        f,t=both["frozen"][q],both["trained"][q];assert f["t"]==t["t"]
        obs=(t["related"]-t["skip"])-(f["related"]-f["skip"])
        observations[q]={"t":t["t"],"trained":[t["related"],t["skip"]],"frozen":[f["related"],f["skip"]],"interaction":obs}
        clusters[t["t"]].append(obs)
    ns=np.array([len(v) for k,v in sorted(clusters.items())]);tot=np.array([sum(v) for k,v in sorted(clusters.items())])
    rng=np.random.default_rng(13);rep=[]
    for _ in range(40):
        indices=rng.integers(0,len(ns),size=(250,len(ns)))
        rep.extend(tot[indices].sum(1)/ns[indices].sum(1))
    out={"n":len(truth),"trajectories":len(clusters),"metric":"Full Support@2048","models":model,"interaction":float(tot.sum()/ns.sum()),
         "trajectory_bootstrap_ci95":np.quantile(rep,[.025,.975]).tolist(),"query_delta_distribution":dict(Counter(r["interaction"] for r in observations.values())),"native_forecast_seal_sha256":hashes,
         "gold_sha256":pilot.sha(OFF/"gold-spans.json.gz")}
    put("interaction-outcomes.json.gz",observations);put("interaction.json",out)
    print(out,flush=True)
if __name__=="__main__":run()
