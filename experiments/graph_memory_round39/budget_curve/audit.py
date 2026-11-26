"""Check sealed outputs against previous studies and elementary trapezoids, without importing the scorer."""
from collections import Counter, defaultdict
from common import D,W,GLOBAL,REMAIN,SEEDS,BUDGETS,ORDERS,SELECTORS,read,sha,save


def near(a,b):
    assert abs(a-b)<1e-11,(a,b)


def main():
    upstream = W/"graph_memory_round35/calibration_transfer"
    previous = read(upstream/"outcomes.json.gz")
    assert sha(upstream/"outcomes.json.gz")==read(upstream/"measure-seal.json")["outcomes"]
    event_counts, byseed = Counter(), {}
    nesting = defaultdict(Counter)
    summary = read(D/"results.json")
    for seed in SEEDS:
        tally = Counter()
        pp, op = D/f"test-{seed}-packets.json.gz", D/f"test-{seed}-outcomes.json.gz"
        assert sha(pp)==read(D/f"test-{seed}-seal.json")["packets"] and sha(op)==read(D/f"test-{seed}-score-seal.json")["outcomes"]
        packets, outcomes = read(pp),read(op)
        glob = read(GLOBAL/f"test-{seed}-pred.json.gz")
        globalscores = read(GLOBAL/f"test-{seed}-outcomes.json.gz")
        # Independently replay both deterministic prefix controls from every original rank and cost.
        feat = read(__import__("pathlib").Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz"))
        costs = {r["q"]:r["c"] for r in feat}
        cal = W/"graph_memory_round35/calibration_scale"
        ranks = {q:{"R35":v["oof_3894"]} for q,v in read(cal/"test-orders.json.gz").items()}
        if seed!=13:
            for j in range(8):
                for q,v in read(upstream/f"orders-{j}.json.gz").items():
                    ranks[q]["R35"]=v[str(seed)]["oof_3894"]
        canonical = W/"graph_memory_round22/native_multiseed/official580"/f"seed-{seed}"
        native = {}
        for name in ORDERS[1:]:
            root=canonical/name
            assert read(root/"results.json")["metrics"]==sha(root/"metrics.json.gz")
            native[name]=read(root/"metrics.json.gz")["graph"]
            for j in range(8):
                for r in read(root/f"picks-{j}.json.gz"):
                    ranks[r["q"]][name]=r["graph"]
        old_p = REMAIN/f"test-{seed}-pred.json.gz"
        old = read(old_p) if old_p.is_file() else None
        if old:
            assert sha(old_p)==read(REMAIN/f"test-{seed}-seal.json")["prediction"]
        for q,(t,ps) in packets.items():
            assert t==outcomes[q][0]==previous[q]["t"]==glob[q][0]
            v=outcomes[q][1]
            for i,arm in enumerate(ORDERS):
                ranked=ranks[q][arm]
                c=costs[q]
                for k,b in enumerate(BUDGETS):
                    head,ff,used,used_ff=[],[],0,0
                    closed=False
                    for unit in ranked:
                        val=c[unit]
                        if not closed and used+val<=b:
                            head.append(unit)
                            used+=val
                        else:
                            closed=True
                        if used_ff+val<=b:
                            ff.append(unit)
                            used_ff+=val
                    assert ps[i][k][:2]==[head,ff]
                    tally["independent_prefix_or_firstfit_lists"]+=2
                for j,policy in enumerate(SELECTORS):
                    scores=v[arm+"/"+policy]
                    tag=arm+"/"+policy
                    adjacent_falls=0
                    for k in range(len(BUDGETS)-1):
                        previous_set=set(ps[i][k][j])
                        next_set=set(ps[i][k+1][j])
                        nesting[tag]["adjacent_comparisons"]+=1
                        nesting[tag]["nonnested_packets"]+=int(not previous_set.issubset(next_set))
                        adjacent_falls+=int(scores[1][k][0]>scores[1][k+1][0])
                        if policy=="strict":
                            assert previous_set.issubset(next_set)
                    nesting[tag]["adjacent_full_to_incomplete"]+=adjacent_falls
                    nesting[tag]["questions_with_any_full_to_incomplete"]+=int(adjacent_falls>0)
                    for col in (0,1):
                        vals=[m[col] for m in scores[1]]
                        near(scores[0][col],(sum(vals)-.5*(vals[0]+vals[-1]))/5.)
                        tally["independent_auc_checks"]+=1
                    for k,b in enumerate(BUDGETS):
                        seq=ps[i][k][j]
                        assert scores[1][k][2:]==[sum(c[p] for p in seq),len(seq)]
                        assert scores[1][k][2]<=b
                        tally["cost_and_size_checks"]+=1
                if old:
                    control=old[q][1][arm]
                    for j,name in enumerate(("strict","firstfit")):
                        assert ps[i][3][j]==control["head"]+control["extra"][name]
                        tally["remaining_budget_2048_lists"]+=1
                if arm=="R35":
                    oo=previous[q]["seeds"][str(seed)]["oof_3894"]
                    auc,curve=v[arm+"/strict"]
                    for a,b in zip((curve[3][0],auc[1],auc[0],curve[3][1]),(oo[0],oo[1],oo[2],oo[4])):
                        near(a,b)
                        tally["R35_original_endpoints"]+=1
                else:
                    oo=native[arm][q]
                    assert oo["t"]==t
                    auc,curve=v[arm+"/strict"]
                    for a,b in zip((auc[0],auc[1],curve[3][0],curve[3][1],curve[2][1],curve[1][1]),
                                   (oo["full_support_auc"],oo["coverage_auc"],oo["full_support_2048"],oo["coverage_2048"],oo["coverage_1024"],oo["coverage_512"])):
                        near(a,b)
                        tally["native_archived_endpoints"]+=1
            for j,method,gref in ((1,"firstfit","R35-firstfit"),(2,"graph_dp","graph-dp")):
                assert ps[0][3][j]==glob[q][1][gref] and v["R35/"+method][1][3]==globalscores[q][1][gref]
                tally["global_packet_2048_packet_and_score_pairs"]+=1
        for arm in summary["arms"]:
            totals=[sum(r[1][arm][0][j] for r in outcomes.values())/len(outcomes) for j in (0,1)]
            for a,b in zip(totals,summary["per_seed"][str(seed)][arm]):
                near(a,b)
        byseed[str(seed)]=dict(tally)
        event_counts.update(tally)
    save(D/"audit.json",dict(per_seed=byseed,counts=event_counts,budget_nesting=nesting,summary_sha256=sha(D/"results.json")))
    print(dict(event_counts))


if __name__=="__main__":
    main()
