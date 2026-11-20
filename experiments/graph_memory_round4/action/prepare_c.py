"""Strictly causal 4 KiB LRU history on SWE-smith. Current range query precedes the event update."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import base64,gzip,json
from pathlib import Path
from prepare import D,R3,w,printed,rel,file,put
def one(j):
    C=R3/"demand"
    raw_ranges=json.loads((D/"range_C.json").read_bytes())
    totals=Counter()
    with file(D/f"input_C_{j}.jsonl.gz") as ai,file(D/f"answer_C_{j}.jsonl.gz") as ag:
        for task in w.rows(C/f"source_{j}.jsonl.gz"):
            i=task["instance"];repo=i.split(".")[0].replace("__","/");state=w.empty("lru")
            metadata={"instance":i,"issue":task["issue"]}
            for t,ev in enumerate(task["events"],1):
                _,args,report=ev;p=rel(args.get("path"))
                if p and args.get('command')=='view':
                    totals["path_views"]+=1
                    vr=raw_ranges[i][str(t)]
                    if isinstance(vr,tuple):vr=list(vr)
                    valid=vr is None or (isinstance(vr,list) and len(vr)==2 and all(type(x) is int for x in vr) and vr[0]>=1 and (vr[1]>=vr[0] or vr[1]==-1))
                    lines=printed(report)
                    if not lines:totals["no_rows"]+=1
                    elif not valid:totals["unparsed_range"]+=1
                    else:
                        put(ai,[i,repo,t,p,vr,{"lru":base64.b64encode(state).decode()}])
                        put(ag,[i,t,sorted(lines.items())]);totals['views']+=1
                state,_=w.transition(state,ev,metadata,None,4096);assert len(state)<=4096
                totals["checkpoints"]+=1
            totals["issues"]+=1
    return totals
if __name__=="__main__":
    with ProcessPoolExecutor(4) as pool:results=list(pool.map(one,range(8)))
    result=sum(results,Counter());(D/"C_counts.json").write_text(json.dumps(result,indent=1),encoding="utf8")
    print(result)
