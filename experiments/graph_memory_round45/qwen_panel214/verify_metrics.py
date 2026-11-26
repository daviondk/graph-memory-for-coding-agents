"""Independently recompute official group/MSS outcomes and the token-limited prefix for all reported rankings."""
import math
from verify import get,sha
def scores(ids,g):
    groups=g["groups"]
    if not groups:return [1.0,1.0,1.0]
    hit=[len(set(v).intersection(ids))>=k for k,w,v in groups]
    alt=any(set(v)<=set(ids) for v in g["alternative"])
    weights=[w for _,w,_ in groups];s=sum(weights)
    return [float(all(hit) or alt),sum(hit)/len(hit),sum(w*h for w,h in zip(weights,hit))/s if s else 0.0]
def main():
    g=get("cal-ordinal-judgments.json.gz");seal=get("audit-seal.json");p=get("panel.json")
    assert sha("cal-ordinal-judgments.json.gz")==seal["data"] and sha("gpu-seal.json")==seal["gpu"] and sha("fusion-seal.json")==seal["fusion"]
    assert set(g)==set(p["order"])
    checks=0
    for prefix, ranked in (("","predictions.json.gz"),("fusion-","fusion-predictions.json.gz"),("matched-","matched-all-ranks.json.gz")):
        rank=get(ranked);out=get(prefix+"outcomes.json.gz");agg=get(prefix+"results.json")
        for q,arms in rank.items():
            row=g[q];index={e:i for i,e in enumerate(row["ids"])};cost=row["cost"]
            for name,listing in arms.items():
                order=[index[e] for e in listing];assert len(order)==len(set(order))==8
                at5=scores(order[:5],row);at8=scores(order,row)
                metric=[at5[0],at8[0]];tokens=[sum(cost[e] for e in order[:5]),sum(cost[e] for e in order)]
                for budget in (2048,6144):
                    kept=[];spent=0
                    for e in order:
                        if spent+cost[e]>budget:break
                        kept.append(e);spent+=cost[e]
                    metric.append(scores(kept,row)[0]);tokens.append(spent)
                metric+=at5[1:2]+at8[1:2]+at5[2:3]
                assert all(math.isclose(v,w,abs_tol=1e-12) for v,w in zip(metric,out[q]["arms"][name],strict=True))
                assert tokens==out[q]["tokens"][name];checks+=1
        for nm,t in agg["panels"].items():
            split=nm.split("_",1)
            qs=dict(outside204=p["remaining"],all214=p["order"],pilot10=p["pilot"])[split[0]]
            if len(split)>1:qs=[q for q in qs if bool(out[q]["seen"])==(split[1]=="overlap")]
            assert len(qs)==t["states"]
            for name,arm in t["methods"].items():
                for j,z in enumerate(arm["returned_tokens"]):assert math.isclose(z,sum(out[q]["tokens"][name][j] for q in qs)/len(qs),abs_tol=1e-10)
    print("Independent MSS, group metrics and exact token costs validated for",checks,"method-state predictions.")
if __name__=="__main__":main()
