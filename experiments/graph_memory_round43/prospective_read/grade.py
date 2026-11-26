"""Evaluate all five sealed outer folds and a future-aware upper bound under the same prefix."""
from collections import Counter
from common import *

PAIRS=(("model","near"),("near","original"),("target","original"),("novel","target"),("near","novel"),("model","original"))


def bounds(ma,mb,A,B,closed):
    delta=int(ma)-int(mb)
    if closed or (ma and mb):return [delta,delta]
    if ma:return [int(not B),1]
    if mb:return [-1,-int(not A)]
    return [-int(bool(B-A)),int(bool(A-B))]


def main():
    seal=read(D/"rank-seal.json");out={}
    for repo,dig in seal["folds"].items():
        f="seal-"+repo[:12]+".json";assert sha(D/f)==dig
        s=read(D/f);name="ranks-"+repo[:12]+".json.gz";assert sha(D/name)==s["rows"]
        rr=read(D/name);assert not (out.keys()&rr.keys());out.update(rr)
    states=read(D/"features.json.gz");meta=bind(F,"packets.json.gz");queries=bind(F,"requests.json.gz")
    existing=bind(F,"outcomes.json.gz");scored={}
    for k,r in states.items():
        bs=r["blocks"];lookup={b["idx"]:b for b in bs};head,remainder=prefix(bs)
        w=queries["windows"][k];run=meta[k]["run"]
        views=[{(n,d):size for n,d,size in queries["by_run"][run][str(at)]} for at in w["reads"]]
        receipt=set(map(tuple,r["receipt"]));all_seen=Counter()
        for v in views:all_seen.update({key:1 for key in set(v)-receipt})
        gain={b["idx"]:sum(all_seen[(n,d)] for n,d,_ in b["novel"]) for b in bs}
        ranks=out[k]|{"oracle":choose(bs,gain)}
        unit_by_m={};scores={}
        for m,seq in ranks.items():
            total=Counter(chosen_bytes=sum(lookup[i]["cost"] for i in seq),
                       nontarget_bytes=sum(lookup[i]["cost"] for i in seq if not lookup[i]["target"]),
                       target_bytes=sum(lookup[i]["cost"] for i in seq if lookup[i]["target"]))
            novelty={(n,d) for i in seq for n,d,_ in lookup[i]["novel"]};unit_by_m[m]=novelty
            total["capacity_units"]=len(novelty)
            for v in views:
                needed=set(v)-receipt;covered=needed&novelty
                total.update(dict(lines=len(covered),bytes=sum(v[atom] for atom in covered),
                       any_view=int(bool(covered)),full_with_receipt=int(not(needed-covered)),
                       full_increment=int(bool(needed) and not(needed-covered))))
            total["hit"]=int(total["lines"]>0)
            total["upper"]=int(total["hit"] or (not w["closed"] and bool(novelty)))
            assert sum(gain[i] for i in seq)==total["lines"]
            scores[m]=dict(total)
        assert all(scores["oracle"]["hit"]>=scores[m]["hit"] and scores["oracle"].get("lines",0)>=scores[m].get("lines",0) for m in METHODS)
        assert scores["oracle"]["hit"]==int(any(gain[b["idx"]]>0 for b in bs if b["idx"] in head or b["cost"]<=remainder))
        assert scores["original"]["hit"]==existing[k]["arms"]["local"]["hit"] and scores["original"].get("lines",0)==existing[k]["arms"]["local"].get("novel_lines",0)
        paired={m+"_minus_"+b:bounds(scores[m]["hit"],scores[b]["hit"],unit_by_m[m],unit_by_m[b],w["closed"]) for m,b in PAIRS}
        dd=existing[k]["demand"]
        scored[k]=dict(repo=r["repo"],issue=r["issue"],held=r["held"],group=r["group"],closed=w["closed"],
            observed=dd.get("observed_demand",0),novel_demand=dd.get("observed_novel",0),demand_lines=sum(all_seen.values()),
            pool_upper=int(any(gain.values())),views=len(views),scores=scores,bounds=paired,oracle_ids=ranks["oracle"])
    save("outcomes.json.gz",scored);save("grade-seal.json",dict(rows=sha(D/"outcomes.json.gz"),ranks=sha(D/"rank-seal.json"),
            requests=sha(F/"requests.json.gz"),existing=sha(F/"outcomes.json.gz"),program=sha(D/"grade.py")))
    print("Graded",len(scored),"out-of-repository forecasts, five rankers and future oracle.")
if __name__=="__main__":main()

