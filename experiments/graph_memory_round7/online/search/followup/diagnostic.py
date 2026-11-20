"""Descriptive audit of common nonempty prediction opportunities and concentration."""
import collections
import json
from evaluate import ROOT,rows,save
pred=iter(rows(ROOT/"predictions.jsonl.gz"))
vis={(r["id"],r["t"]):r for r in rows(ROOT/"visits.jsonl.gz")}
summary=collections.defaultdict(list)
for i,t,arms in pred:
    value=vis.get((i,t))
    if not value:
        continue
    hits=value["hit"]
    summary[value["panel"]].append((i,arms[0] is not None,arms[1] is not None,hits[1]-hits[0]))
out={}
for panel,g in summary.items():
    both=[v for v in g if v[1] and v[2]]
    sums=collections.Counter()
    sizes=collections.Counter()
    for i,_,_,delta in g:
        sums[i]+=delta
        sizes[i]+=1
    loo=[(sum(sums.values())-sums[i])/(len(g)-sizes[i]) for i in sizes]
    out[panel]={"all_reads":len(g),"both_nonempty":len(both),"wins_matched":sum(v[3]>0 for v in both),
                "losses_matched":sum(v[3]<0 for v in both),"typed_only_nonempty":sum((not b) and a for _,b,a,_ in g),
                "issues_with_net_gain":sum(x>0 for x in sums.values()),
                "largest_one_issue_gain":max(sums.values()),"leave_one_issue_out_delta_pp":[100*min(loo),100*max(loo)]}
print(out)
save(ROOT/"diagnostic.json",out)
