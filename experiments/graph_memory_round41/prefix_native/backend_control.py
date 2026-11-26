"""Secondary same-device end-of-history filtering on the predefined technical subset."""
from collections import Counter,defaultdict
from shared import D,W,OFF,SEEDS,ARMS,read,save,sha,pack


def main():
    gold=W/"graph_memory_round34/interval_witness/test-atoms.json.gz"
    stats=read(D/"scoring.json")
    assert sha(gold)==stats["atoms"] and sha(D/"outcomes.json.gz")==stats["scores"]
    atoms=read(gold)
    outcomes={r["q"]:r for r in read(D/"outcomes.json.gz")}
    totals=defaultdict(Counter)
    for sh in range(8):
        src=D/f"forecast-{sh}.json.gz"
        assert sha(src)==read(D/f"forecast-{sh}-seal.json")["data"]
        orders={(q,cut):o for q,t,cut,o in read(src)}
        costs={r["q"]:[n["token_count"] for n in r["rr"]] for r in read(W/"graph_memory_round19/trained_rank"/f"forecasts-main-{sh}.json.gz")}
        for (q,cut),full in orders.items():
            if cut!=100:
                continue
            r=outcomes[q]
            groups=["all"]+(["eligible"] if not r["pilot"] and r["eligible"] else [])
            for seed in SEEDS:
                for arm in ARMS:
                    k=f"{seed}/{arm}"
                    visible=set(orders[q,50][k])
                    actual=pack(orders[q,50][k],costs[q],False)
                    same_cpu=pack([i for i in full[k] if i in visible],costs[q],False)
                    def fs(ids):
                        choice=set(ids)
                        return int(all(not choice.isdisjoint(ind) for _,a,b,ind in atoms[q]))
                    causal=fs(actual)
                    assert causal==r["arms"][str(seed)][arm+"/firstfit"][0]
                    for g in groups:
                        count=totals[f"{g}/{arm}"]
                        count.update(dict(q_seed=1, actual=causal,cpu_final_filtered=fs(same_cpu),
                            gpu_final_filtered=r["arms"][str(seed)][arm+"/final_restricted_firstfit"][0],
                            same_delivery=set(actual)==set(same_cpu)))
    save(D/"backend-control.json",dict(groups=totals,scoring=sha(D/"scoring.json")))
    print(dict(totals))


if __name__=="__main__":
    main()
