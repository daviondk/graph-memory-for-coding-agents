"""Secondary budget sensitivity. See COST_SENSITIVITY.md before interpretation."""
import collections
import gzip
import json
from evaluate import ROOT,trajectories,finish,cost,save,digest,write

def run():
    orig=json.loads((ROOT/"results.json").read_bytes())
    decisions=list(trajectories())
    outcome=[]
    for r in decisions:
        slot=None
        seen=collections.defaultdict(set)
        history={}
        for t,ev in enumerate(r["events"],1):
            if ev is None:
                continue
            k,p,ns=ev
            if slot:
                if k in ("view","shell"):
                    row=finish(slot,"read",(p,ns))
                    lo=1+16*((slot["anchors"][0]-1)//16)
                    common=set(ns)&set(range(lo,lo+16)) if p==slot["path"] else set()
                    row["unseen_in_prior_address_history"]=len(common-seen[p])
                    row["fits_one_aligned_page"]=(min(ns)-1)//16==(max(ns)-1)//16
                else:
                    row=finish(slot,"replaced" if k=="search" else "edit")
                outcome.append(row)
                slot=None
            if k=="search":
                slot=dict(id=r["id"],repo=r["repo"],panel=r["panel"],t=t,path=p,anchors=[ns[0],history.get(p,1)],grep=ns)
            else:
                history[p]=sorted(ns)[(len(ns)-1)//2]
            seen[p].update(ns)
        if slot:
            outcome.append(finish(slot,"end"))
    summary={}
    with gzip.GzipFile(str(ROOT/"persistent_cost_rows.jsonl.gz"),"wb",mtime=0) as out:
        for row in outcome:write(out,row)
    for panel in orig:
        group=[q for q in outcome if q["panel"]==panel]
        info=cost(group)
        assert info["attempts"]==orig[panel]["cost"]["attempts"]
        info["unseen_in_prior_address_history"]=sum(q.get("unseen_in_prior_address_history",0) for q in group)
        info["fits_one_aligned_page_oracle"]=sum(q.get("fits_one_aligned_page",False) for q in group)
        info["short16"]=cost([q for q in group if q["short16"]])
        summary[panel]=info
        print(panel,info["attempts"],info["eligible_reads"],info["search"],info["unseen_in_prior_address_history"],info["fits_one_aligned_page_oracle"])
    save(ROOT/"persistent_cost.json",summary)
if __name__=="__main__":
    run()
