"""Third representation: compare projected rows with what the next logged model query actually contained."""
import collections,concurrent.futures,hashlib,json,urllib.request
from pathlib import Path
import acquire as a
D=a.D
def audit(r):
    i=r["instance_id"];url=a.S3+i+"/"+i+".traj"
    with urllib.request.urlopen(url,timeout=55) as stream:
        if int(stream.headers.get("content-length",-1))>a.LIMIT:return i,{"over_cap":1}
        raw=stream.read(a.LIMIT+1)
    if len(raw)>a.LIMIT:return i,{"over_cap":1}
    obj=json.loads(raw);projected,ct=a.project(obj,r);co=collections.Counter()
    if not projected:return i,{"filtered":1}
    for j,rec in enumerate(obj["trajectory"][:-1]):
        name,args,obs=projected["events"][j]
        if name=="other":continue
        nxt=obj["trajectory"][j+1].get("query") or []
        if not nxt or nxt[-1].get("role")!="tool":
            co["next_query_missing"]+=1;continue
        ids=nxt[-1].get("tool_call_ids",[])
        prev=nxt[-2] if len(nxt)>1 else {}
        tools=prev.get("tool_calls") or []
        if len(ids)!=1 or len(tools)!=1 or tools[0].get("id")!=ids[0] or a.canon(prev.get("action",""))!=a.canon(rec["action"]):
            co["next_query_unpaired"]+=1;continue
        co["paired_model_queries"]+=1
        v=a.printed(a.text(nxt[-1].get("content")));given=a.printed(obs)
        co["projected_rows_checked"]+=len(given);co["present_in_next_query"]+=sum(v.get(n)==s for n,s in given.items())
        if not all(v.get(n)==s for n,s in given.items()):co["non_identical_scopes"]+=1
    return i,dict(co)
def main():
    all_=json.loads((D/"selection.json").read_bytes());chosen=sorted(all_,key=lambda r:a.h(("queryaudit|"+r["instance_id"]).encode()))[:10]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:result=dict(ex.map(audit,chosen))
    totals=dict(sum((collections.Counter(v) for v in result.values()),collections.Counter()))
    a.save("query_audit.json",{"by_issue":result,"totals":totals});print(totals)
if __name__=="__main__":main()
