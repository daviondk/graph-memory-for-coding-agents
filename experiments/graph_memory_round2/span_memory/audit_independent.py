"""Independent audit of R2-F. Reconstruct labels, decisions and oracle; compare exact solver to enumeration."""
import collections
import gzip
import hashlib
import itertools
import json
import math
import re
from pathlib import Path

import numpy as np
import run as method

D = Path(__file__).resolve().parent
E = D.parent / "edit_memory"
PACK = E.parents[1] / "memory_session5" / "packets"

def sha(x):
    return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()

def read(p):
    return json.loads(p.read_bytes())

def lines(p):
    with gzip.open(p, "rt", encoding="utf8") as src:
        for line in src: yield json.loads(line)

def oracle_span(pages, path, target):
    # Sort line ranges by coordinate instead of relying on original page ordering by file.
    candidates=sorted((p[1],p[2],p[4],j) for j,p in enumerate(pages) if p[0]==path)
    contiguous=[]
    for r in candidates:
        if not contiguous or contiguous[-1][-1][1]+1!=r[0]:contiguous.append([])
        contiguous[-1].append(r)
    matches=[]
    for group in contiguous:
        text="\n".join(r[2] for r in group)
        cursor=0
        while (k:=text.find(target,cursor))>=0:
            start=group[0][0]+text.count("\n",0,k)
            end=start+target.count("\n")
            matches.append([idx for a,b,_,idx in group if a<=end and b>=start])
            if len(matches)>1:return []
            cursor=k+1
    return matches[0] if matches else []

def attempts(events,step):
    for _,a,feedback in events[step:step+4]:
        if a.get("command")!="str_replace": continue
        raw=a.get("path"); target=a.get("old_str")
        if not isinstance(raw,str) or not isinstance(target,str) or not target:continue
        relative=raw.removeprefix("/testbed/").removeprefix("./")
        if not relative or relative.startswith("/") or ".." in relative.split("/"):continue
        ok=bool(re.search(r"(?:The file .*? has been edited\.|successfully replaced)",feedback[:1300],re.I))
        yield relative,target,ok

def brute(pages,slate,weights):
    # Enumerate each selectable subset and each possible start, then count only entire
    # intervals which remain inside it; independent of the pair / triple expansion.
    if len(slate)<=3:return tuple(slate)
    local={s:i for i,s in enumerate(slate)}
    nxt={(p[0],p[1]):i for i,p in enumerate(pages)}
    next_index={i:nxt.get((pages[i][0],pages[i][2]+1)) for i in slate}
    best=-1.; selected=None
    for S in itertools.combinations(slate,3):
        U=set(S);score=0.
        for j in S:
            i=j
            for t in range(3):
                if i not in U:break
                score+=weights[local[j],t]
                i=next_index[i]
        if score>best:
            best=score;selected=S
    return selected

def check_solver():
    gen=np.random.default_rng(798304)
    counts=collections.Counter()
    for n in [0,1,2,3,4,5,8,12,16,25,36,48]:
        for rep in range(6):
            seq=[];position=collections.defaultdict(lambda:1)
            for i in range(n+3):
                path=str(gen.integers(1,4))
                a=position[path]+int(gen.integers(0,3)==0)
                b=a+int(gen.integers(1,12));position[path]=b+1
                seq.append((path,a,b,0,""))
            idx=gen.permutation(len(seq))[:n].tolist()
            W=gen.random((n,4)) if rep else np.zeros((n,4))
            goal=brute(seq,idx,W)
            got=tuple(method.exact(seq,idx,{(r[0],r[1]):i for i,r in enumerate(seq)},W))
            assert goal==got,(n,rep,goal,got)
            counts[n]+=1
    return counts

def main():
    split=read(E/"split.json");test=set(split["test"]);train=set(split["all"])-test
    assert not train&test
    old={a for records in read(PACK/"selection.json").values() for a,k,j in records}
    old.update(a for a,k,j in read(PACK/"transfer/selection.json"))
    all_previous={i for sh in split["shards"] for i in sh["ids"]}
    ids={i for i,k,j in read(D/"selection.json")}
    assert len(ids)==len(read(D/"selection.json")) and not (ids & (old|all_previous))
    assert all(i.split(".")[0] in test and int(sha("compact-s4|"+i),16)%10 for i in ids)
    for lock,base in [(D/"method_lock.json",D),(D/"decision_lock.json",D),(E/"method_lock.json",E)]:
        for n,digest in read(lock).items():assert sha((base/n).read_bytes())==digest
    # The primary scorer is read only at the end for verification against our independent counts.
    arms=("recent","pointwise","global","history","typed","placebo")
    totals=collections.Counter();stats=collections.defaultdict(collections.Counter);costs=collections.Counter()
    processed=set();observed=set();eligible=set();revision_width=collections.Counter();seeds=check_solver()
    later_hits=collections.Counter();later_oracle=0
    rng=np.random.default_rng(789432);active=future_wins=oracle=all_cuts=real_solver_checks=excluded_later=0
    for k in range(8):
        pred={(i,t):(p,chars) for i,t,p,chars in lines(D/f"pred_{k}.jsonl.gz")}
        gold={(i,t):(span,x) for i,t,span,x in lines(D/f"gold_{k}.jsonl.gz")}
        assert len(pred)==sum(1 for _ in lines(D/f"pred_{k}.jsonl.gz"))
        assert len(gold)==sum(1 for _ in lines(D/f"gold_{k}.jsonl.gz"))
        for obj in lines(D/f"fresh_{k}.jsonl.gz"):
            iid=obj["instance"];repo=iid.split(".")[0]
            assert iid not in processed and iid in ids;processed.add(iid)
            assert repo in test and repo not in train
            for t,seq,idx,meta,hist,last in method.stream(obj):
                key=(iid,t);obs=list(attempts(obj["events"],t))
                if obs and not obs[0][2] and any(a[2] for a in obs[1:]):excluded_later+=1
                ranked,cost=pred.pop(key);observed.add(iid);all_cuts+=1
                for a in arms:
                    assert len(set(ranked[a]))==min(3,len(idx)) and set(ranked[a])<=set(idx)
                    assert cost[a]==sum(len(seq[p][4]) for p in ranked[a])
                if real_solver_checks==k and len(idx)>3:
                    # Prefix invariance: replacing suffix by one inert item does not change the candidate buffer.
                    partial={**obj,"events":obj["events"][:t]+[["padding",{},""]]}
                    last_state=list(method.stream(partial))[-1]
                    assert last_state[0]==t and last_state[1]==seq and last_state[2]==idx
                    weights=rng.random((len(idx),4)); links={(r[0],r[1]):i for i,r in enumerate(seq)}
                    assert brute(seq,idx,weights)==tuple(method.exact(seq,idx,links,weights))
                    real_solver_checks+=1
                if not obs or not obs[0][2]:
                    assert key not in gold
                    accepted=next((o for o in obs if o[2]),None)
                    if accepted is not None:
                        later_span=oracle_span(seq,accepted[0],accepted[1])
                        later_oracle+=int(bool(later_span) and len(set(later_span))<=3 and set(later_span)<=set(idx))
                        for a in arms:later_hits[a]+=int(bool(later_span) and set(later_span)<=set(ranked[a]))
                    continue
                path,oldtext,_=obs[0]
                exact=oracle_span(seq,path,oldtext)
                can=int(bool(exact) and set(exact)<=set(idx) and len(set(exact))<=3)
                assert (exact,can)==gold.pop(key)
                active+=1;eligible.add(iid);oracle+=can;revision_width[len(exact)]+=1
                outcome={a:int(bool(exact) and set(exact)<=set(ranked[a])) for a in arms}
                for a in arms:
                    totals[a]+=outcome[a];costs[a]+=cost[a]
                    stats[a][repo]+=outcome["typed"]-outcome[a]
                    stats[a][("wins",)]+=int(outcome["typed"]>outcome[a])
                    stats[a][("losses",)]+=int(outcome["typed"]<outcome[a])
                stats["counts"][repo]+=1
        assert not pred and not gold
    assert processed==ids
    report=read(D/"results.json")
    assert all_cuts==report["all_cuts"] and active==report["n"] and oracle==report["upper_bound"]
    assert set(totals)==set(report["hits"]) and dict(totals)==report["hits"]
    assert sorted(revision_width.items())==sorted((int(x),y) for x,y in report["gold_width"].items())
    assert len(observed)==report["seen_instances"] and len(eligible)==report["included_instances"]
    for a in arms:
        r=report["typed_minus"][a]
        assert abs(costs[a]/active-report["mean_characters"][a])<1e-9
        assert stats[a][("wins",)]==r["wins"] and stats[a][("losses",)]==r["losses"]
        assert all([stats[a][s],n]==r["by_project"][s] for s,n in stats["counts"].items())
    out={"status":"passed","checks":"independent enumeration of possible three-page sets vs implementation, prefix invariance on one stream per shard, held-out project and instance separation across all selection manifests and compact-s4 bucket, all method/content hashes, independent exact contiguous target reconstruction and eligibility for every cut, oracle, paired win/loss, count and characters by arm",
         "synthetic_objective_instances":sum(seeds.values()),"synthetic_by_slate_size":seeds,"real_objective_and_prefix_examples":real_solver_checks,
         "previous_project_count":len(train),"heldout_project_count":len(test),"new_selected":len(ids),"included_projects":len(stats["counts"]),
         "all_cuts":all_cuts,"eval_cuts":active,"evaluated_instances":len(eligible),"ceiling":oracle,"first_failed_but_later_accepted_excluded_cuts":excluded_later,"hits":totals,
         "posthoc_first_accepted_sensitivity":{"different_windows":excluded_later,"additional_oracle":later_oracle,"additional_hits":later_hits,"all_eligible":active+excluded_later,"hits":{a:totals[a]+later_hits[a] for a in arms}},
         "interpretation":"Window is eligible exactly when its first attempted nonempty str_replace with a valid path is accepted. A failed first attempt suppresses the window even if another succeeds inside it. Comparison concerns offline replay and first-attempt policy. Uncalibrated pointwise start weights and estimated widths make this exact optimization of a surrogate; probabilistic optimality requires a calibrated joint distribution."}
    (D/"audit_independent.json").write_text(json.dumps(out,indent=2),encoding="utf8")
    print(json.dumps(out))
if __name__=="__main__":main()

