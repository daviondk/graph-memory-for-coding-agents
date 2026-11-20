"""Check projection against the actual next model prompt on ten hash-selected published trajectories."""
import hashlib,json,urllib.request,sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
from acquire_k import HERE,ROOT,read,save,acquire
from shared import rows
DATA={r["instance"]:r for p in sorted(HERE.glob("source_*.jsonl.gz")) for r in rows(p)}
RC={r["id"]:r for r in read(HERE/"receipts.json")}
def audit(i):
    rc=RC[i];co=Counter()
    with urllib.request.urlopen(urllib.request.Request(rc["url"],headers={"User-Agent":"memory-transfer-audit"}),timeout=40) as f:data=f.read(acquire.LIMIT+1)
    assert hashlib.sha256(data).hexdigest()==rc["sha256"]
    s=json.loads(data);tasks=s["trajectory"]
    for j,tr in enumerate(tasks[:-1]):
        name,args,obs=DATA[i]["events"][j]
        if name=="other":continue
        q=tasks[j+1].get("query") or []
        if len(q)<2 or q[-1].get("role")!="tool":
            co["missing_native_next_tool"]+=1;continue
        call=q[-2];ids=q[-1].get("tool_call_ids",[]);tc=call.get("tool_calls") or []
        if len(ids)!=1 or len(tc)!=1 or ids[0]!=tc[0].get("id") or acquire.canon(tr["action"])!=acquire.canon(call.get("action","")):
            co["next_query_unpaired"]+=1;continue
        co["paired_queries"]+=1
        seen=acquire.printed(acquire.text(q[-1].get("content")));projected=acquire.printed(obs)
        co["projected"]+=len(projected);co["found"]+=sum(seen.get(n)==line for n,line in projected.items())
    return i,co
def main():
    ids=sorted(DATA,key=lambda i:hashlib.sha256(("r4kaudit|"+i).encode()).hexdigest())[:10]
    with ThreadPoolExecutor(5) as pool:results=dict(pool.map(audit,ids))
    co=sum(results.values(),Counter());save(HERE/"audit_display.json",dict(chosen=results,totals=co));print(co)
if __name__=="__main__":main()
