"""Independent portable verification with no weights, live benchmarks or network."""
import hashlib,json
from itertools import combinations
from pathlib import Path
from collections import Counter
from math import isclose
HERE=Path(__file__).resolve().parent
def read(n):return json.loads((HERE/n).read_bytes())
def sha(n):return hashlib.sha256((HERE/n).read_bytes()).hexdigest()
def audit():
    p=read("plan.json"); seal=read("ranking-seal.json");meas=read("measurement-seal.json")
    assert seal["complete"] and set(seal["forecasts"])==set(p["panel"]) and len(p["panel"])==8
    assert sha("run.py")==p["code"] and sha("PROTOCOL_RU.md")==p["protocol"] and seal["plan"]==sha("plan.json")
    assert meas["outcomes"]==sha("outcomes.json") and meas["forecast_seal"]==sha("ranking-seal.json")
    result=read("results.json");out=read("outcomes.json");extra=read("overflow-results.json");c=read("counterfactual-results.json")
    assert extra["outcomes"]==meas["outcomes"] and c["forecast_seal"]==sha("ranking-seal.json")
    count=Counter();full_exact=Counter();dyn_exact=Counter();all_mask=0
    for q,h in seal["forecasts"].items():
        path="forecasts/"+q+".json";assert sha(path)==h
        f=read(path);n=len(f["full"]["doc_order"]);edges=f["full"]["pairs"];order=f["full"]["doc_order"]
        assert len(set(order))==n==10 and len(set(frozenset(row[:2]) for row in edges))==45
        assert all(edges[i][2]>=edges[i+1][2] for i in range(44))
        records={tuple(r["ban"]):r for r in out[q]["records"]}
        cf=c["rows"][q];regions=cf["regions"]
        raw_winners={};blind_family={};oracle_min={};expected_k=Counter()
        for k in range(n+1):
            for banned in combinations(range(n),k):
                allowed=set(range(n))-set(banned);s=set(i for i in order if i in allowed)
                gate=set(sorted(s,key=order.index)[:2]);bits=sum(1<<b for b in banned)
                valid=[j for j,(u,v,_) in enumerate(edges) if {u,v}<=allowed]
                dynamic=next((j for j in valid if {edges[j][0],edges[j][1]}&gate),None)
                rhs=[j for j,_,failed,alive in regions if not alive&bits and failed&bits==failed]
                assert rhs==([] if dynamic is None else [dynamic]);all_mask+=1
                if dynamic is not None:
                    oracle_min.setdefault(dynamic,k)
                if k<=2:
                    r=records[banned]
                    assert (r["dyn"],r["full"])==(dynamic,valid[0])
                    blind_family[dynamic]=True;raw_winners[valid[0]]=True
                    if k==2:
                        count["k2"]+=1
                        full_exact.update({key:int(value==valid[0]) for key,value in r["full_got"].items()})
                        dyn_exact.update({key:int(value==dynamic) for key,value in r["dyn_got"].items()})
                if k in (3,4):expected_k[k]+=1
        assert all(cf["minimum_withdrawal_masks"][str(e)].bit_count()==v for e,v in oracle_min.items())
        assert set(out[q]["dyn_pair_only"])==set(out[q]["dyn_tree"])==set(blind_family)
        assert set(out[q]["static_tree"])==set(raw_winners)
        for k,n_events in expected_k.items():
            item=extra["by_question"][q][str(k)]
            assert item["events"]==n_events
            for key in ("same","per_root","prefix","union"):assert item[key+"_accepted"]==item[key+"_correct"]
    assert all_mask==8192 and count["k2"]==360
    report=result["all"]["k"]["2"]
    assert full_exact==report["full_exact"] and dyn_exact==report["dynamic_exact"]
    stock=read("stock-probe.json");sp=read("stock-plan.json")
    assert stock["plan"]==sha("stock-plan.json") and sorted(stock["rows"])==sorted(sp["panel"])
    for q,both in stock["rows"].items():
        for name,row in both.items():
            assert row["same_winner"] and row["matched_keys"] and row["direct_beam"]==row["expected_beam"]
            assert row["max_pair_abs"]<1e-4 and row["count"]==(17 if name=="full" else 13)
    baseline=read("official-reference.json")["by_group"]["all"];assert baseline["questions"]==7405 and baseline["both"]==7204
    manifest=HERE/"manifest.json"
    if manifest.exists():
        hs=read("manifest.json")
        assert set(hs)=={x.relative_to(HERE).as_posix() for x in HERE.rglob("*") if x.is_file() and "__pycache__" not in x.parts and x!=manifest}
        assert all(sha(name)==h for name,h in hs.items())
    return {"questions":len(seal["forecasts"]),"all_masks":all_mask,"two_removals":count["k2"],"stock_model_cases":4}
if __name__=="__main__":print(audit())
