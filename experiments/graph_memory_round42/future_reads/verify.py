"""Standard-library offline verifier, including exhaustive tests of censoring bounds on toy futures."""
import itertools
from collections import defaultdict
from data import D,METHODS,read,sha
from score import PAIRS,pair_bounds


def bounds_test():
    universe=set(range(3));subsets=[set(v) for n in range(4) for v in itertools.combinations(universe,n)]
    cases=0
    for A in subsets:
        for B in subsets:
            for past in subsets:
                ma=bool(A&past);mb=bool(B&past)
                d=[int(ma or bool(A&f))-int(mb or bool(B&f)) for f in subsets]
                assert pair_bounds(ma,mb,A,B,False)==[min(d),max(d)]
                assert pair_bounds(ma,mb,A,B,True)==[int(ma)-int(mb)]*2
                cases+=1
    return cases


def main():
    p=read(D/"packets.json.gz");requests=read(D/"requests.json.gz");a=read(D/"outcomes.json.gz");r=read(D/"results.json")
    assert len(p)==2696 and set(p)==set(a)==set(requests["windows"])
    assert sha(D/"PROTOCOL_RU.md")==read(D/"packet-seal.json")["protocol"]
    assert sha(D/"packets.json.gz")==read(D/"packet-seal.json")["packets"]
    assert sha(D/"requests.json.gz")==read(D/"request-seal.json")["requests"]
    assert sha(D/"outcomes.json.gz")==read(D/"score-seal.json")["outcomes"]
    assert sha(D/"score-seal.json")==r["source"]
    for k,z in p.items():
        req=requests["windows"][k];receipt=set(map(tuple,z["receipt"]))
        views=[{(n,d):size for n,d,size in requests["by_run"][z["run"]][str(v)]} for v in req["reads"]]
        for m in METHODS:
            set_m={(n,d) for n,d,s in z["by_method"][m]}
            hits=[(set(v)-receipt)&set_m for v in views];out=a[k]["arms"][m]
            assert sum(map(len,hits))==out.get("novel_lines",0)
            assert sum(sum(v[j] for j in hit) for v,hit in zip(views,hits))==out.get("novel_bytes",0)
            assert bool(out["hit"])==any(hits)
            assert sum(set(v)<=set_m|receipt for v in views)==out.get("full_with_receipt",0)
    for n,ids in (("held1071",[k for k,v in p.items() if v["held"]]),("all2696",list(p)),("main676",[k for k,v in p.items() if v["group"]=="main"])):
        t=r["panels"][n];assert t["episodes"]==len(ids)
        for m in METHODS:
            for f in ("hit","upper","novel_lines","novel_bytes","full_with_receipt"):
                assert t["methods"][m].get(f,0)==sum(a[k]["arms"][m].get(f,0) for k in ids)
        for m,b in PAIRS:
            groups=defaultdict(list)
            for k in ids:groups[p[k]["issue"]].append(a[k]["arms"][m]["hit"]-a[k]["arms"][b]["hit"])
            assert abs(sum(sum(g)/len(g) for g in groups.values())/len(groups)-t["contrasts"][m+"_minus_"+b]["macro"])<1e-10
    assert bounds_test()==512
    if (D/"manifest.json").exists():
        for f,d in read(D/"manifest.json")["files"].items():assert sha(D/f)==d,f
    print("Verified 2696 packet windows, every observed informative request, all seven methods, summaries and 512 censoring-bound fixtures.")


if __name__=="__main__":main()

