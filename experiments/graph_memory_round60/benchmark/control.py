"""Budget-matched rank-confidence alternatives with exact integration over ties."""
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import groupby
import math
from common import HERE,load,save,sha

def priorities(q):
    r=q["ranks"]
    intersection=set.intersection(*(set(r[k][:5]) for k in ("bm25_outcome","sparse_fields","fusion")))
    return {"overlap_top5":5-len(intersection),"cross_encoder_demotion":r["minilm"][:5].index(r["fusion"][0])}

def schedules():
    inputs=load(HERE/"inputs.json.gz")[:99]
    blind=load(HERE/"decisions.json.gz")[:99]
    ids=defaultdict(list)
    for i,r in enumerate(inputs):ids[r["repo"]].append(i)
    prior=[priorities(q) for q in inputs]
    result={}
    for policy in prior[0]:
        parts={}
        for repo,rows in ids.items():
            remaining=sum(not blind[i]["skip_three"] for i in rows)
            definite=[];uncertain=[];choose=0
            ranked=sorted(rows,key=lambda i:-prior[i][policy])
            for _,it in groupby(ranked,key=lambda i:prior[i][policy]):
                batch=list(it)
                if len(batch)<=remaining:
                    definite+=batch;remaining-=len(batch)
                else:
                    if remaining:
                        uncertain=batch;choose=remaining
                    break
            parts[repo]={"take":definite,"tie":uncertain,"tie_count":choose}
        assert sum(len(v["take"])+v["tie_count"] for v in parts.values())==31
        result[policy]=parts
    save("control-schedules.json",result)
    save("control-seal.json",{n:sha(HERE/n) for n in ("control-schedules.json","CONTROL_PROTOCOL.md","control.py")})

def grade():
    assert all(sha(HERE/n)==h for n,h in load(HERE/"control-seal.json").items())
    items=load(HERE/"per_item.json.gz")[:99]
    results={}
    for method,byrepo in load(HERE/"control-schedules.json").items():
        baseline=sum(r["hit"]["fusion"] for r in items)
        fixed=[]
        ways={0:1}
        expected_nt=Fraction()
        all_tied=0
        def delta(i):return int(items[i]["hit"]["full"])-int(items[i]["hit"]["fusion"])
        for v in byrepo.values():
            fixed+=v["take"]
            tied=v["tie"];k=v["tie_count"]
            if not tied:continue
            all_tied+=len(tied)
            expected_nt+=Fraction(k,len(tied))*sum(items[i]["score"]["full"][1] for i in tied)
            ways_here={(0,0):1}
            for i in tied:
                next_ways=dict(ways_here)
                for (n,d),count in ways_here.items():
                    if n<k:
                        key=n+1,d+delta(i);next_ways[key]=next_ways.get(key,0)+count
                ways_here=next_ways
            p={d:c for (n,d),c in ways_here.items() if n==k}
            assert sum(p.values())==math.comb(len(tied),k)
            comb=Counter()
            for a,n in p.items():
                for b,m in ways.items():comb[a+b]+=n*m
            ways=comb
        total=sum(ways.values())
        expected_nt+=sum(items[i]["score"]["full"][1] for i in fixed)
        base=baseline+sum(delta(i) for i in fixed)
        distribution={str(base+d):str(c) for d,c in sorted(ways.items())}
        expected=base+Fraction(sum(d*c for d,c in ways.items()),total)
        p73=Fraction(sum(c for d,c in ways.items() if base+d>=73),total)
        results[method]={"expected":float(expected),"expected_input_tokens":float(expected_nt),
                         "range":[base+min(ways),base+max(ways)],"p_at_least_73":float(p73),"distribution":distribution,
                         "definite":len(fixed),"randomly_selected_among_ties":31-len(fixed),"tied_pool":all_tied}
    save("control-results.json",results)
    for k,v in results.items():print(k,v["range"],v["expected"],v["p_at_least_73"],v["expected_input_tokens"])
if __name__=="__main__":
    import sys
    if "--score" in sys.argv:grade()
    else:schedules()

