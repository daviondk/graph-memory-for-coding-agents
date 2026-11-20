"""Replay previously observed unit-test outcomes; no future inputs, grader or canonical implementation is an argument."""
from concurrent.futures import ThreadPoolExecutor
import time
from base import D,read,save,sha,execute,stable
from policy import mutations,POLICIES,write,bytes_used,BUDGET
def main():
    files=["PROTOCOL_RU.md","prepare.py","runner.py","safe_ast.py","base.py","policy.py","write.py","past.json.gz","screening.json"]
    save("writer_lock.json",{n:sha((D/n).read_bytes()) for n in files})
    tasks=read("past.json.gz");packets=[];out=[];raw=[];start=time.monotonic()
    with ThreadPoolExecutor(8) as pool:
        for task in tasks:
            cards=task["cards"];bank=mutations(task["source"],task["id"])
            rows=list(pool.map(execute,[dict(source=s,name=task["name"],examples=cards) for s in bank]))
            matrix=[row["bits"] if row.get("status")=="ok" else [0]*len(cards) for row in rows]
            memories={a:[] for a in POLICIES};steps=[]
            for idx,card in enumerate(cards):
                mask=sum((1<<h) for h,col in enumerate(matrix) if not col[idx]);item=[idx,card,mask]
                for arm in POLICIES:
                    memories[arm]=write(memories[arm],item,arm,len(bank)-1 or 1)
                    assert arm=="all" or bytes_used(memories[arm])<=BUDGET
                steps.append({a:[x[0] for x in mem] for a,mem in memories.items()})
            picks={}
            for arm,mem in memories.items():
                losses=[sum(1-col[x[0]] for x in mem) for col in matrix]
                picks[arm]=min(range(len(bank)),key=lambda j:(losses[j],j))
            packets.append(dict(id=task["id"],name=task["name"],source=task["source"],memory=memories))
            out.append(dict(id=task["id"],sources=bank,picks=picks,events=steps,indices={a:[x[0] for x in m] for a,m in memories.items()}))
            raw.append(dict(id=task["id"],rows=rows))
    save("packets.json.gz",packets);save("alternatives.json.gz",out);save("mutation_observations.json.gz",raw)
    save("write_receipt.json",{"physical_programs":sum(len(x["rows"]) for x in raw),"seconds":time.monotonic()-start,"packets":sha((D/"packets.json.gz").read_bytes())})
    print("packets",len(packets),"distinct fail/union",sum(p["memory"]["failed"]!=p["memory"]["union"] for p in packets),flush=True)
if __name__=="__main__":main()

