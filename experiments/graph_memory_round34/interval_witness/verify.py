"""Finite model check using independent direct set-union over selected nodes, tied scores and budgets."""
from geometry import *
from itertools import product,combinations,permutations
from math import log
def synthetic():
    n=3;universe={0,1,2};groups=[set(i for i in universe if mask&(1<<i)) for mask in range(1,2**n)]
    costs=[2,1,4];contexts=0;budgets=0;ties=0
    for gs in product(groups,repeat=2):
        for scores in product(range(3),repeat=n):
            order=sorted(range(n),key=lambda i:(-scores[i],i));rank={node:j+1 for j,node in enumerate(order)}
            cover=lambda prefix:all(set(prefix)&g for g in gs)
            truth=next(j for j in range(n+1) if cover(order[:j]))
            lex=min(max((scores[i],-i) for i in g) for g in gs);assert order[truth-1]==-lex[1]
            assert truth==max(min(rank[i] for i in g) for g in gs)
            low=min(max(scores[i] for i in g) for g in gs);assert low==lex[0]
            ties+=sum(s==low for s in scores)>1
            compact=[g for g in gs if not any(h<g for h in gs)]
            assert truth==max(min(rank[i] for i in g) for g in compact)
            neg=universe-set.union(*gs)
            used=sum(costs[i] for i in order[:truth]);before=sum(costs[i] for i in order[:truth] if i in neg)
            bound=sum(costs[i]*np.logaddexp(0,scores[i]-low)/log(2) for i in neg);assert before<=bound+1e-12
            for cap in range(8):
                prefix=[];total=0
                for i in order:
                    if total+costs[i]>cap:break
                    prefix.append(i);total+=costs[i]
                assert cover(prefix)==(used<=cap);budgets+=1
            contexts+=1
    return dict(orders_families=contexts,orders_with_ambiguously_tied_scalar_threshold=ties,prefix_budget_cases=budgets)
def main():
    r=load(D/"results.json");sel=load(D/"selection.json");assert r["chosen"]==sel["chosen"]
    at=load(D/"test-atoms.json.gz");cost=load(D/"test-costs.json.gz");rows=load(D/"test-outcomes.json.gz");rn=load(D/"test-ranks.json.gz")
    w=r["chosen"]["witness"];fx=r["chosen"]["fixed"];hard=r["chosen"]["cost_log"];proxy=Counter()
    for q in rows:
        a=at[q];s=cost[q][w]
        if s["atomic_prefix_tokens"]<=2048<s["all_positive_prefix_tokens"]:
            proxy["all_disagreements"]+=1;proxy["alternative_minimal"]+=any(len(g)>1 for g in buckets(a));proxy["redundant_overlap"]+=bool({i for *_,g in a for i in g}-{g[0] for g in buckets(a) if len(g)==1})
        assert rn[q][w]==rn[q][fx] and rows[q]["arms"][hard][0]==rows[q]["arms"][w][0]
    assert proxy["all_disagreements"]==20
    for stage in ["train","dev","test"]:
        assert sha(D/(stage+"-atoms.json.gz"))==load(D/(stage+"-geometry.json"))["atoms"]
    for stage in ["dev","test"]:
        assert sha(D/(stage+"-ranks.json.gz"))==load(D/(stage+"-rank-seal.json"))["ranks"]
    assert load(D/"test-rank-seal.json")["selection"]==sha(D/"selection.json")
    assert sel["fit"]==sha(D/"models.json") and sel["evaluator"]==sha(D/"measure.py")
    assert r["outcomes"]==sha(D/"test-outcomes.json.gz")
    cert=load(D/"models.json")["cert"];assert max(v["gap"] for v in cert.values())<1e-6
    out=dict(finite=synthetic(),test_prefix_mismatches=dict(proxy),rank_equality_witness_fixed=sum(rn[q][w]==rn[q][fx] for q in rows),
        benchmark_outcome_sha=r["outcomes"],model_gap=max(v["gap"] for v in cert.values()))
    save(D/"audit.json",out);print(out)
if __name__=="__main__":main()