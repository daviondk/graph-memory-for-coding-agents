"""Separate address disappearance, a pre-existing destination, and witnessed invocation."""
import collections
import gzip
import json
from call_edge import definitions,flag
from prepare import ROOT,load,save
from route import clustered


def audit():
    old_q={r["case"]:r for r in load("queries.json")}
    trans_q={r["case"]:r for r in load("transfer-queries.json")}
    trans_p={r["case"]:r for r in load("transfer-predictions.json")}
    identity={r["case"]:r for r in load("identity-cases.json")}
    original={r["case"]:r["origin"] for r in load("outcomes.json")}
    cases=[]
    for r in load("call-edge-cases.json"):
        cid=r["case"]
        if cid in old_q:
            q=old_q[cid]; bef=q["old"]; aft=q["new"]; origin=original[cid]
        else:
            q=trans_q[cid]; bef=q["before"]; aft=q["commit"]; origin=trans_p[cid]["old_address"]
        cases.append(dict(case=cid, group=r["group"], commit=r["commit"], origin=origin,winner=r["winner"], accepted=r["accepted"],
              target_ok=r["correct"], flag=r["flag"],project=q["project"], before=bef,after=aft))
    rq={r["case"]:r for r in load("reverse-queries.json")}
    rp={r["case"]:r for r in load("reverse-predictions.json")}
    for r in load("reverse-outcomes.json"):
        cid=r["case"]; q=rq[cid]; p=rp[cid]
        cases.append(dict(case=cid,group="reverse_"+r["role"],commit=r["commit"],origin=p["origin"],winner=p["pool"][p["top"]],
                  accepted=r["accepted"],target_ok=r["role"]=="caller" and r["correct_target"],
                  flag=r["flagged"], project=q["project"],before=q["old"],after=q["new"]))
    groups=collections.defaultdict(list)
    for r in cases:
        proj,bef,aft=r["project"],r["before"],r["after"]
        path,qual,_=r["origin"]; dest,other,line=r["winner"]
        gone=qual not in definitions(proj,aft,path) and (path,qual)!=(dest,other)
        older=definitions(proj,bef,dest).get(other,[])
        existed=gone and len(older)==1
        invoked=existed and qual.split(".")[-1] in older[0][1]
        closed=invoked and flag(proj,bef,aft,r["origin"],r["winner"])
        assert bool(r["accepted"] and closed)==r["flag"]
        r["policies"]={k:bool(r["accepted"] and not blocked) for k,blocked in
            dict(no_gate=False,disappearance=gone,existed=existed,called_before=invoked,call_lost=closed).items()}
        groups[r["group"]].append(r)
    summary={}
    for name,g in groups.items():
        stats={}
        for policy in g[0]["policies"]:
            stats[policy]=dict(accepted=sum(r["policies"][policy] for r in g),
                    accepted_true_identity=sum(r["policies"][policy] and r["target_ok"] for r in g))
        summary[name]=dict(n=len(g),commits=len({r["commit"] for r in g}),policies=stats)
    helper=groups["reverse_helper"]
    summary["reverse_false_acceptance_change_ci"]=clustered(helper,
        lambda r:r["policies"]["call_lost"]-r["policies"]["no_gate"],lambda r:1)
    save("ablation-edge-cases.json",cases);save("ablation-edge-results.json",summary)
    print(json.dumps(summary,indent=2))
if __name__=="__main__":
    audit()
