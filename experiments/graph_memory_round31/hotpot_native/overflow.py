"""Verify per-root upper bounds for deletions beyond the precomputed failure budget."""
from collections import Counter
from itertools import combinations
from run import HERE, put, read, sha


def best(rows, removed, roots):
    return next((pair for pair in rows if not set(pair)&removed and set(pair)&roots),None)


def solve(kept, raw, first_four, removed):
    """Only stored ids/orders enter. No global ranks or omitted candidate texts."""
    roots=set([i for i in first_four if i not in removed][:2])
    output={"same":None,"per_root":None,"prefix":None,"union":None,"unchecked":None}
    scans=0
    if len(roots)<2:
        return output,scans,"unknown_root"
    prefix=best(raw,removed,roots)
    candidate=best(kept,removed,roots)
    output.update(prefix=prefix,unchecked=candidate,union=prefix)
    if candidate is None:
        return output,scans,"absent"
    bounds=set()
    position={p:i for i,p in enumerate(kept)}
    single=False
    for k in range(3):
        for cut in combinations(sorted(removed),k):
            scans+=1
            sub=set(cut)
            old_roots=set([i for i in first_four if i not in sub][:2])
            prior=best(kept,sub,old_roots)
            assert prior is not None
            if prior==candidate and old_roots==roots:
                single=True
            if position[prior]>=position[candidate]:
                bounds|=old_roots&roots
    if single:
        output["same"]=candidate
    if bounds==roots:
        output["per_root"]=candidate
        assert prefix is None or candidate==prefix
        output["union"]=candidate
    assert not single or bounds==roots
    return output,scans,"known_root"


def main():
    seal=read(HERE/"measurement-seal.json")
    assert sha(HERE/"outcomes.json")==seal["outcomes"]
    plan=read(HERE/"overflow-plan.json")
    assert sha(HERE/"OVERFLOW_RU.md")==plan["protocol"]
    results=read(HERE/"outcomes.json")
    detail={};aggregate={}
    for q,measured in results.items():
        full=read(HERE/"forecasts"/(q+".json"))["full"]
        edges=[tuple(sorted(row[:2])) for row in full["pairs"]]
        order=full["doc_order"]
        kept=[edges[i] for i in measured["dyn_pair_only"]]
        assert set(measured["dyn_pair_only"])==set(measured["dyn_tree"])
        data={}
        for k in (3,4):
            counts=Counter()
            for mask in combinations(order,k):
                removed=set(mask);roots=set([i for i in order if i not in removed][:2])
                truth=best(edges,removed,roots)
                got,scans,reason=solve(kept,edges[:len(kept)],order[:4],removed)
                counts["events"]+=1;counts["subset_checks"]+=scans;counts[reason]+=1
                for m,pair in got.items():
                    counts[m+"_accepted"]+=int(pair is not None)
                    counts[m+"_correct"]+=int(pair==truth)
                    if m!="unchecked":assert pair in (None,truth)
                counts["extra_over_same"]+=int(got["per_root"] is not None and got["same"] is None)
                counts["prefix_only"]+=int(got["prefix"] is not None and got["per_root"] is None)
                counts["root_only"]+=int(got["per_root"] is not None and got["prefix"] is None)
            data[k]=dict(counts)
            aggregate.setdefault(k,Counter()).update(counts)
        detail[q]=data
    put(HERE/"overflow-results.json",{"plan":sha(HERE/"overflow-plan.json"),"code":sha(HERE/"overflow.py"),
                                     "outcomes":seal["outcomes"],"by_question":detail,"pooled":aggregate})
if __name__=="__main__":main()
