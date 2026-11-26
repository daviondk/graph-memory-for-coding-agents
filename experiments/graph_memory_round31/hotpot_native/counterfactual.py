"""Construct minimal intervention witnesses for a gated pair; verify the exact event probabilities."""
from collections import Counter,defaultdict
from itertools import combinations
from math import prod
from run import HERE,put,read,sha

def code(ids):
    return sum(1<<i for i in ids)

def forced_areas(order,pairs):
    index={d:i for i,d in enumerate(order)}
    certificate=[]
    for roots in combinations(order,2):
        gate=code(roots)
        blocked=code(order[:max(index[r] for r in roots)+1])&~gate
        for rank,(a,b) in enumerate(pairs):
            edge=(1<<a)|(1<<b)
            if not edge&gate:continue
            live_mask=edge|gate
            if not live_mask&blocked:
                certificate.append((rank,gate,blocked,live_mask))
            outside=edge&~gate
            if not outside:
                break
            blocked|=outside
    return certificate

def target(order,pairs,banned):
    roots=code([d for d in order if not banned&(1<<d)][:2])
    return next((i for i,e in enumerate(pairs) if not code(e)&banned and code(e)&roots),None)

def mass(probs,failed,alive):
    return prod(p if failed&(1<<r) else (1-p if alive&(1<<r) else 1) for r,p in enumerate(probs))

def evaluate(full):
    order=full["doc_order"];pairs=[r[:2] for r in full["pairs"]]
    n=len(order);allbits=(1<<n)-1
    areas=forced_areas(order,pairs)
    witness={}
    for rank,gate,failed,alive in areas:
        w=witness.get(rank)
        if w is None or (failed.bit_count(),failed)<(w.bit_count(),w):witness[rank]=failed
    outcomes=[target(order,pairs,r) for r in range(1<<n)]
    observed={}
    for r,e in enumerate(outcomes):
        # Two nested loops provide a deliberately direct, independent oracle for each state.
        hits=[k for k,g,req,live in areas if not live&r and (req&r)==req]
        assert hits==([] if e is None else [e])
        if e is not None:observed[e]=min(r.bit_count(),observed.get(e,n))
    assert all(observed[e]==r.bit_count() and outcomes[r]==e for e,r in witness.items())
    assert set(observed)==set(witness)==set(range(len(pairs)))
    settings={"p005":[.05]*n,"p020":[.20]*n,"p050":[.50]*n,"heterogeneous":[.025+.04*i for i in range(n)]}
    scenarios={}
    for label,probabilities in settings.items():
        tab=defaultdict(float);oracle=defaultdict(float)
        for rank,gate,req,live in areas:
            tab[rank]+=mass(probabilities,req,live)
        tab[None]=mass(probabilities,allbits,0)+sum(mass(probabilities,allbits^(1<<i),1<<i) for i in range(n))
        for r,e in enumerate(outcomes):oracle[e]+=mass(probabilities,r,allbits^r)
        error=max(abs(tab[e]-oracle[e]) for e in oracle)
        assert abs(sum(tab.values())-1)<1e-12 and error<1e-12
        scenarios[label]={"no_result":tab[None],"no_change":tab[outcomes[0]],"changed_to_another_pair":1-tab[None]-tab[outcomes[0]],"max_abs_error":error}
    return {"areas":len(areas),"masks":len(outcomes),"histogram":dict(Counter(r.bit_count() for r in witness.values())),
            "minimum_withdrawal_masks":witness,"regions":areas,"scenarios":scenarios}

def main():
    sealed=read(HERE/"ranking-seal.json")
    records={}
    for q,expected in sealed["forecasts"].items():
        path=HERE/"forecasts"/(q+".json")
        assert sha(path)==expected
        records[q]=evaluate(read(path)["full"])
    put(HERE/"counterfactual-results.json",{"forecast_seal":sha(HERE/"ranking-seal.json"),"spec":sha(HERE/"COUNTERFACTUAL_RU.md"),
                                           "code":sha(HERE/"counterfactual.py"),"rows":records})
if __name__=="__main__":main()
