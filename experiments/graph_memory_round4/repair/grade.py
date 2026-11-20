"""Assess only fixed choices, by function, on disjoint EvalPlus arguments and the original observed CI."""
import math
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from base import D,read,save,sha,execute
from policy import POLICIES,pretty,bytes_used
from decide import rec

def pair(x,y):
    d=np.asarray(x)-np.asarray(y)
    rng=np.random.default_rng(11926);b=rng.integers(0,len(d),(10000,len(d)))
    wins=int(sum(d>0));loss=int(sum(d<0));n=wins+loss
    p=min(1.,2*sum(math.comb(n,j) for j in range(min(wins,loss)+1))/2**n) if n else 1.
    return {"delta":float(d.mean()),"ci":np.quantile(d[b].mean(axis=1),[.025,.975]).tolist(),"wins":wins,"losses":loss,"p_exact":p}
def run(t):
    past,fut,alternatives,packet,assigned,sel=t
    n=len(fut["novel"]);h=len(past["cards"]);source={}
    rows={}
    def put(name,code):
        k=sha(code);source[k]=code;rows[name]=k
    for a,key in assigned.items():
        p=rec(past,key,"calls");put("qwen_"+a,p["source"])
    for a,j in alternatives["picks"].items():put("mut_"+a,alternatives["sources"][j])
    for j,c in enumerate(sel["candidates"]):put("blind_"+str(j),c["source"])
    for a,v in sel["plans"].items():put("choose_"+a,sel["candidates"][v["chosen"]]["source"])
    receipts={}
    for k,code in source.items():
        data=execute(dict(source=code,name=past["name"],examples=past["cards"]+fut["novel"])) if code else {"status":"invalid"}
        bits=data.get("bits",[0]*(h+n));assert len(bits)==h+n
        receipts[k]=dict(status=data["status"],old=sum(bits[:h]),new=sum(bits[h:]),bits=bits,errors=data.get("errors",[]))
    metrics={a:dict(hit=int(receipts[k]["new"]==n),new=receipts[k]["new"],old=receipts[k]["old"],status=receipts[k]["status"],hash=k) for a,k in rows.items()}
    return {"id":past["id"],"historical":h,"n":n,"methods":metrics,"receipts":receipts,
        "memory_bytes":{a:bytes_used(m) for a,m in packet["memory"].items()},"distinct_inputs":assigned["failed"]!=assigned["union"],
        "blind_oracle":max(metrics["blind_"+str(j)]["hit"] for j in range(3))}
def main():
    assert all(sha((D/n).read_bytes())==h for n,h in read("choices_lock.json").items())
    tasks=read("past.json.gz");future=read("future.json.gz");alts=read("alternatives.json.gz");packets=read("packets.json.gz");assign=read("assign.json");sels=read("selected_candidates.json.gz")
    jobs=[]
    for t,f,a,p,s in zip(tasks,future,alts,packets,sels,strict=True):
        assert t["id"]==f["id"]==a["id"]==p["id"]==s["id"]
        jobs.append((t,f,a,p,assign[t["id"]],s))
    with ThreadPoolExecutor(6) as pool:scores=list(pool.map(run,jobs))
    save("per_task.json.gz",scores)
    overview={}
    for k in scores[0]["methods"]:
        v=[x["methods"][k] for x in scores]
        overview[k]={"all":sum(a["hit"] for a in v),"new_passes":sum(a["new"] for a in v),"past_passes":sum(a["old"] for a in v),
                     "new_task_macro":float(np.mean([a["new"]/x["n"] for a,x in zip(v,scores)])),"status":dict(Counter(a["status"] for a in v))}
    contrast={}
    def hits(k):return [x["methods"][k]["hit"] for x in scores]
    for pairnames in [("qwen_union","qwen_failed"),("qwen_union","qwen_empty"),("choose_union","choose_failed"),("choose_read_split","choose_read_failed"),
                      ("choose_read_split","choose_union"),("choose_all","choose_empty"),("mut_union","mut_failed"),("mut_union","mut_individual")]:
        a,b=pairnames;contrast[a+"-"+b]=pair(hits(a),hits(b))
    primary=["qwen_union-qwen_failed","choose_union-choose_failed","choose_read_split-choose_read_failed"]
    hold=0
    for j,k in enumerate(sorted(primary,key=lambda k:contrast[k]["p_exact"])):
        hold=max(hold,min(1,contrast[k]["p_exact"]*(len(primary)-j)));contrast[k]["p_holm"]=hold
    native={}; usage=Counter()
    for folder in ("calls","sample_calls"):
        for p in (D/folder).glob("*.gz"):
            r=read(p)["reply"];assert r["id"] not in native
            native[r["id"]]=r["choices"][0]["finish_reason"]
            for k in ("prompt_tokens","completion_tokens"):usage[k]+=r["usage"][k]
    mean_bytes={arm:float(np.mean([t["memory_bytes"][arm] for t in scores])) for arm in POLICIES}
    lengths={arm:Counter(len(x["memory"][arm]) for x in packets) for arm in POLICIES}
    oldpath=D.parents[1]/"memory_session5/live";prev=set()
    for p in [oldpath/"roster.json",oldpath/"transfer/roster.json"]:
        if p.is_file():prev.update(read(p)["ids"])
    records=read("selection_observations.json.gz")
    active=sum(len(set(x["chosen"] for k,x in row["plans"].items() if k in ("read_split","read_failed")))>1 for row in sels)
    result={"tasks":len(scores),"new_inputs":sum(x["n"] for x in scores),"old_inputs":sum(x["historical"] for x in scores),"scores":overview,"pairs":contrast,
        "bytes_mean":mean_bytes,"lengths":lengths,"blind_oracle":sum(x["blind_oracle"] for x in scores),"graph_failed_different_prompts":sum(x["distinct_inputs"] for x in scores),
        "different_read_choices":active,"reused_task_ids_session5":len(prev&set(assign)),"native_calls":len(native),"usage":dict(usage),"finish":dict(Counter(native.values())),
        "archive_forward_function_inputs":sum(len(x["witnesses"])*len(x["witnesses"][0]) for x in records),"scored_unique_programs":sum(len(t["receipts"]) for t in scores)}
    save("results.json",result)
    print("finished",len(scores),len(native),{a:overview[a]["all"] for a in overview},flush=True)
if __name__=="__main__":main()

