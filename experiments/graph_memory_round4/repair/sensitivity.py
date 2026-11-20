"""Descriptive follow-up only. Check past regressions and the exact split of previously used task IDs."""
from collections import Counter
from base import D,read,save
from grade import pair

def main():
    prev=set()
    for p in ("roster.json","transfer/roster.json"):
        prev.update(read(D.parents[1]/"memory_session5/live"/p)["ids"])
    rows=read("per_task.json.gz");groups={}
    for k,subset in [("all",rows),("previously_seen",[r for r in rows if r["id"] in prev]),("new_id",[r for r in rows if r["id"] not in prev])]:
        report={}
        for a in ("qwen_empty","qwen_failed","qwen_union"):
            v=[s["methods"][a] for s in subset]
            for score in ["new_only","past_only","past_and_new"]:
                b=[int((score=="past_only" or x["hit"]) and (score=="new_only" or x["old"]==r["historical"])) for x,r in zip(v,subset)]
                report.setdefault(score,{})[a]=b
        groups[k]={"n":len(subset),"counts":{s:{a:sum(b) for a,b in v.items()} for s,v in report.items()},"paired":{s:pair(m["qwen_union"],m["qwen_failed"]) for s,m in report.items()}}
    save("sensitivity.json",groups)
if __name__=="__main__":main()

