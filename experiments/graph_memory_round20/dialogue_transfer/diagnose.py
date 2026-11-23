"""Post hoc analytic random and role-stratified controls, requiring no fitted target weights."""
import collections
import json
import math
import numpy as np
import study as s
from score import load,write

def main():
    data=json.loads(s.TARGET.read_bytes())
    sel=set(load("split.json.gz")["selected"])
    tab=collections.defaultdict(list)
    role_len=collections.defaultdict(list)
    raw_by_question={}
    rawvariants=collections.defaultdict(set)
    for q in data:
        qh=s.digest(q["question_id"])
        ids=[s.digest(k) for k in q["haystack_session_ids"]]
        raw_by_question[qh]=ids
        ts=[v for sess in q["haystack_sessions"] for v in sess]
        g=sum(x.get("has_answer") is True for x in ts)
        for sess in q["haystack_sessions"]:
            pairs=[(x["role"],x["content"]) for x in sess]
            rawvariants[s.sig(pairs)].add(s.digest(json.dumps(pairs,ensure_ascii=False)))
        for x in ts:
            role_len["target_positive" if x.get("has_answer") is True else "target_other"].append(len(x["content"].split()))
        if not g:
            continue
        n=len(ts)
        u=sum(x["role"]=="user" for x in ts)
        gu=sum(x["role"]=="user" and x.get("has_answer") is True for x in ts)
        k=math.ceil(.20*n)
        role=(min(k,u)*gu/max(1,u) + max(0,k-u)*(g-gu)/max(1,n-u))/g
        for key in ("all", "strict" if qh in sel else "other"):
            tab[key].append((k/n,role))
    for row in s.ds.load_groups("locomo",locomo_path=str(s.LO))[0]:
        role_len["source_positive" if row.label else "source_other"].append(len(row.text.split()))
    conflicts={k for k,v in rawvariants.items() if len(v)>1}
    split=load("split.json.gz")
    metrics=load("group-metrics.json.gz")["external"]
    clean=[k for k,hs in split["histories"].items() if not conflicts.intersection(hs)]
    usable=[k for k in clean if metrics[k]["p"]]
    ctrls={k:dict(uniform_expected=float(np.mean(v,axis=0)[0]),user_stratum_first_expected=float(np.mean(v,axis=0)[1]),n=len(v)) for k,v in tab.items()}
    sens={a:sum(metrics[k]["arms"][a]["metric"]["R20"] for k in usable)/len(usable) for a in s.ARMS}
    write("observed-session-ids.json.gz",raw_by_question)
    out=dict(controls=ctrls,median_words={k: float(np.median(v)) for k,v in role_len.items()},
             unambiguous=dict(histories=len(clean),usable=len(usable),R20=sens))
    write("diagnostics.json",out)
    print(out)
if __name__=="__main__":
    main()
