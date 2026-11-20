"""Recompute the main comparisons from archived observations (standard library only)."""
import json
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parent
def read(name):
    return json.loads((R/name).read_bytes())
def lines(name):
    return [json.loads(s) for s in (R/name).read_text(encoding="utf8").splitlines()]
def check_binding():
    root="revalidation/binding/"
    first=lines(root+"decisions.jsonl");second=lines(root+"outcomes.jsonl")
    assert len(first)==len(second)
    metrics={name:Counter() for name in ["headers","global","positive","selective"]}
    n=0
    for a,b in zip(first,second):
        assert all(a[k]==b[k] for k in ["panel","project","new","path","caller"])
        assert (a["old_answer"]==b["new_answer"])==b["same"]
        if a["panel"]!="transfer":continue
        n+=1
        for name in metrics:
            if not a["reuse"][name]:outcome="reread"
            elif b["same"]:outcome="correct"
            else:outcome="stale"
            metrics[name][outcome]+=1
    assert n==717 and [(metrics[m]["reread"],metrics[m]["stale"]) for m in ["global","selective","headers"]]==[(321,0),(244,0),(244,0)]
    return n
def main():
    online=read("online/search/followup/results.json")
    costs=read("online/search/followup/persistent_cost.json")
    panels=["kimi","claude","kimi_replication"]
    assert [(online[p]["reads"],online[p]["hit"][0],online[p]["hit"][1],online[p]["hit"][3]) for p in panels]==[(210,10,33,43),(348,18,32,32),(225,21,34,51)]
    assert [(costs[p]["attempts"],costs[p]["search"]["full"]) for p in panels]==[(57,7),(42,0),(63,0)]
    loc=read("localization/results.json")
    assert [(loc[s]["n"],loc[s]["n_files_hit"],loc[s]["arms"]["bm25"]["tasks_hit"],loc[s]["arms"]["doclink"]["tasks_hit"]) for s in ("sympy-reused","sphinx-external")]==[(30,17,12,6),(24,9,8,5)]
    front=read("localization/frontier/results.json")
    assert [(front["arms"][x]["file"],front["arms"][x]["packet"]) for x in ("old","init","rare","import")]==[(10,9),(12,10),(13,10),(12,10)]
    gpu=read("reader/results.json")
    assert gpu["n"]==gpu["controls"]==8 and [gpu["totals"][x]["strict_pass"] for x in ("bm25","doclink")]==[2,0]
    print("Verified: 3 search panels, 54 line-localization tasks, 20 independent file-ranking tasks,",
          gpu["n"],"paired Qwen tasks and",check_binding(),"transfer queries for versioned memory.")
if __name__=="__main__":main()
