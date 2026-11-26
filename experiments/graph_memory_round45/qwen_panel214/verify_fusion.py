"""Independent, standard-library replay of three reciprocal-rank fusions and all published counts."""
from fractions import Fraction

from verify import get, sha


def main():
    panel=get("panel.json");base=get("fusion-local-full.json.gz");qw=get("qwen-scores.json.gz")
    local=get("fusion-local-seal.json");seal=get("fusion-seal.json");r=get("fusion-results.json")
    pred=get("fusion-predictions.json.gz");out=get("fusion-outcomes.json.gz")
    assert local["protocol"]==sha("FUSION_PROTOCOL_RU.md") and local["forecasts"]==sha("fusion-local-full.json.gz")
    assert seal["local"]==sha("fusion-local-seal.json") and seal["gpu"]==sha("gpu-seal.json")
    assert seal["forecasts"]==sha("fusion-predictions.json.gz") and r["outcomes"]==sha("fusion-outcomes.json.gz")
    assert r["seal"]==sha("fusion-seal.json") and set(base)==set(qw)==set(out)==set(pred)==set(panel["order"])
    for q,v in base.items():
        ids=v["ids"];score=qw[q]["scores"]
        # For identical cosines the stable ordinal rank follows input candidate order.
        ordered=sorted(range(len(ids)),key=lambda j:(-score[ids[j]],j))
        qr={idx:rank for rank,idx in enumerate(ordered,1)}
        assert pred[q]["qwen"]==qw[q]["ranks"]["qwen"] and pred[q]["qwen_seen"]==qw[q]["ranks"]["qwen_seen"]
        for name,other in v["ranks"].items():
            assert set(other)==set(range(1,len(ids)+1))
            full=sorted(range(len(ids)),key=lambda j:(
                -(Fraction(1,60+qr[j])+Fraction(1,60+other[j])),ids[j]))
            observed=v["seen"]
            assert [ids[j] for j in full[:8]]==pred[q][name]
            assert [ids[j] for j in sorted(full,key=lambda x:observed[x])[:8]]==pred[q][name+"_seen"]
    for panelname,subset in (("all214",panel["order"]),("outside204",panel["remaining"]),("pilot10",panel["pilot"])):
        for name,value in r["panels"][panelname]["methods"].items():
            assert [sum(out[q]["arms"][name][i] for q in subset) for i in range(4)]==value["complete_counts"]
    print("Verified all reciprocal-rank fusions across all 214 states and three score panels.")


if __name__=="__main__":main()

