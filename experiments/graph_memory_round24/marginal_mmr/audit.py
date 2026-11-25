"""Re-score all methods with an independent interval sweep and repeat external document clustering."""
from collections import Counter
from pathlib import Path
import sys,importlib,importlib.util
from io24 import D,R,read,sha,save,PAIRS
from evaluate import pairs_inference
def sweep(base,op,gold):
    from collections import defaultdict
    by=defaultdict(list)
    for i,series in enumerate((base,[op[:3]] if op else [],gold)):
        for e,l,h in series:
            if l<h:by[e].extend(((l,i,1),(h,i,-1)))
    den=seen=added=chars=0
    for ev in by.values():
        depths=[0,0,0];prev=0
        for p,j,w in sorted(ev):
            n=p-prev;i,o,g=depths
            if g:
                den+=n
                if i or o:seen+=n
                if o and not i:added+=n
            if o and not i:chars+=n
            depths[j]+=w;prev=p
        assert depths==[0,0,0]
    assert den>0
    return int(seen==den),seen/den,added,chars
def main(name):
    picks=read(D/f"{name}-choices.json.gz");ops=read(D/f"{name}-opened.json.gz")
    outcomes=read(D/f"{name}-per-query.json.gz");res=read(D/f"{name}-results.json")
    module=importlib.import_module(name);gold=module.targets(picks)
    sr=read(R/("marginal_open/per-query.json.gz" if name=="ise" else "marginal_transfer/per-query.json.gz"))
    if name=="mdd":sr=sr["rows"]
    k=0;eqchecks=0;oldchecks=0
    for r in outcomes:
        q=r["q"];base=picks[q]["base"];actions=ops[q]
        for a,z in r["values"].items():
            crit=sweep(base,actions["arms"][a],gold[q])
            assert crit==(z["fs"],z["cov"],z["new_gold"],z["new"]);k+=1
        for a,states in r["equal"].items():
            for z,op in zip(states,actions["equal"][a]):
                assert (z["fs"],z["cov"],z["new_gold"],z["new"])==sweep(base,op,gold[q]);eqchecks+=1
            assert states[0]["tokens"]==states[1]["tokens"]
        for a in ("bm25","first_positive","rank_novelty"):
            z=r["values"][a]
            if name=="ise":
                h=sr[q]["arms"][a];old=[h["union_fs"],h["union_coverage"],h["gold_gain_chars"],h["added_source_chars"],h["open_tokens"]]
            else:old=sr[q]["values"][a][:5]
            assert [z[f] for f in ("fs","cov","new_gold","new","tokens")]==old;oldchecks+=1
    assert len(gold)==len(ops)==len(outcomes)==res["n"]
    val={"n":len(ops),"sweep_cost_pairs":eqchecks,"sweep_all":k,"historical_controls_checked":oldchecks,"results_sha":sha(D/f"{name}-results.json")}
    if name=="mdd":
        for z in outcomes:
            targets={e for e,l,h in gold[z["q"]]};assert len(targets)==1;z["t"]=next(iter(targets))
        val["document_sensitivity"]=pairs_inference(outcomes)
    dest=D/f"{name}-audit.json"
    if dest.exists():assert read(dest)==val
    else:save(dest,val)
    print(k,eqchecks,oldchecks)
if __name__=="__main__":main(sys.argv[1])
