"""Score the independently sealed selection archive with native and independent metrics."""
from collections import defaultdict
import dataclasses
from statistics import mean
import sys
import numpy as np
from predict import HERE,OFF,E5,POLICIES,check_plan,digest,load,save,bm_shard
sys.path.insert(0,str(OFF))
from discover import pilot
from verify_package import evaluate as independent
from score import compare

def grade():
    check_plan();seal=load(HERE/"forecast-seal.json")
    assert seal["plan"]==digest(HERE/"plan-seal.json") and seal["forecasts"]==digest(HERE/"forecasts.json.gz")
    assert seal["dense_seal"]==digest(E5/"forecast-seal.json") and seal["bm25_seal"]==digest(OFF/"forecast-lock.json")
    gold=load(OFF/"gold-spans.json.gz")
    cards={r["q"]:r for r in load(HERE/"forecasts.json.gz")}
    assert set(gold)==set(cards)
    outcomes=[];group=defaultdict(dict)
    for i in range(8):
        dense={r["q"]:r for r in load(E5/f"forecasts-main-{i}.json.gz")}
        for q,t,bm in bm_shard(i):
            card=cards[q]
            assert t==card["t"]==dense[q]["t"] and i==card["shard"]
            pool={n["node_id"]:pilot.RankedNodeRecord.model_validate(n) for n in bm["ranked"]}
            keys=sorted(pool);g=tuple(pilot.SourceSpan.model_validate(s) for s in gold[q])
            arms={"rrf/"+arm:[keys[j] for j in card["arms"][arm]] for arm in POLICIES}
            for arm in POLICIES:
                arms["e5/"+arm]=dense[q]["arms"][arm];arms["bm25/"+arm]=bm["arms"][arm]
            for arm,ids in arms.items():
                assert len(ids)==len(set(ids))
                selected=tuple(pool[n] for n in ids)
                cost=sum(n.token_count for n in selected)
                assert cost<=2048
                metrics=pilot.span_metrics_under_token_budget(selected,g,2048)
                alt=independent(gold[q],[s.model_dump() for n in selected for s in n.source_spans])
                assert all(abs(a-getattr(metrics,k))<1e-12 for a,k in zip(alt,("full_support","coverage","density"),strict=True))
                row=dict(q=q,t=t,arm=arm,tokens=cost,nodes=len(ids),**dataclasses.asdict(metrics))
                assert q not in group[arm]
                group[arm][q]=row;outcomes.append(row)
    assert len(outcomes)==24000
    summaries={arm:{"n":len(rs),"fs_count":int(sum(r["full_support"] for r in rs.values())),
        **{k:mean(r[k] for r in rs.values()) for k in ("tokens","nodes","coverage","density","f1","full_support")}}
        for arm,rs in group.items()}
    contrasts={ref:compare(group["rrf/related"],group[ref]) for ref in ("e5/related","rrf/skip","bm25/related","rrf/value")}
    res=dict(summaries=summaries,comparisons=contrasts,trajectory_count=len({r["t"] for r in outcomes}),
        query_count=len(cards),forecasts_sha256=digest(HERE/"forecast-seal.json"),gold_sha256=digest(OFF/"gold-spans.json.gz"))
    save("outcomes.json.gz",outcomes);save("results.json",res)
    print([(k,v["fs_count"],round(v["tokens"],2)) for k,v in summaries.items()])
    print(contrasts)
if __name__=="__main__":grade()
