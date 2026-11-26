"""Classify excluded IDs using raw structural counts only."""
from panel import *
import re
from collections import Counter
def main():
    plan=load(D/"plan.json");hist={}
    for s in range(8):hist.update(load(D/f"histories-{s}.json.gz"))
    out={}
    for tid,z in hist.items():
        if z["status"]=="retained":continue
        sh,off,n=plan["panel"][tid];p=RAW/"trajectories"/f"trajectories-{sh:05d}.jsonl"
        with p.open("rb") as f:f.seek(off);b=f.read(n)
        assert hashlib.sha256(b).hexdigest()==z["record_sha"];obj=json.loads(b)
        calls=Counter();outs=Counter();unexpected=0;misordered=0;missingid=0
        for m in obj["messages"]:
            if m["role"]=="assistant":
                for c in m.get("tool_calls",[]) or []:calls[c["id"]]+=1
            if m["role"]=="tool":
                k=m.get("tool_call_id")
                if k is None:missingid+=1
                elif k not in calls:misordered+=1
                outs[k]+=1
        out[tid]={"status":z["status"],"calls":sum(calls.values()),"outs":sum(outs.values()),"duplicated_call_ids":sum(v>1 for v in calls.values()),"duplicated_output_ids":sum(v>1 for v in outs.values()),
              "unmatched_calls":sum((calls-outs).values()),"unmatched_outputs":sum((outs-calls).values()),"outputs_before_call":misordered,"output_without_id":missingid}
    save(D/"excluded.json",out);print(out)
if __name__=="__main__":main()
