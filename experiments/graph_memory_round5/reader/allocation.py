"""Reproduce the slot allocation on the fixed reader panel before opening its labels."""
from collections import defaultdict
from pathlib import Path
import heapq,sys
from evidence import D,R4,trim,tok
from infer import read,sha,save
from data_io import rows
T=D.parent/"retrieval";sys.path.insert(0,str(T))
from budget import base,soft,monotone
import numpy as np
def main():
    weights=np.asarray(read(T/"budget_model.json")["base"]["weights"])
    data=sorted(read("A_packets.json.gz"),key=lambda x:sha("budget5|"+x["id"]))
    by=defaultdict(dict)
    for x in data:by[x["file"]][x["local_index"]]=x
    for file,idx in by.items():
        for i,r in enumerate(rows(R4/"repo/archive_inputs"/file,["context"])):
            if i in idx:idx[i]["texts"]=r["context"]
    out=[]
    for off in range(0,len(data),32):
        group=data[off:off+32];counts=[min(3,len(v["rank"])) for v in group]
        marg=[monotone(soft(base(np.arange(1,len(x["rank"])+1))@weights)[:8]) for x in group]
        depth=[1]*len(group);queue=[(-m[1],i,2) for i,m in enumerate(marg) if len(m)>1];heapq.heapify(queue)
        for slot in range(sum(counts)-len(group)):
            _,i,d=heapq.heappop(queue);depth[i]=d
            if d<len(marg[i]):heapq.heappush(queue,(-marg[i][d],i,d+1))
        assert sum(depth)==sum(counts)
        for x,f,d in zip(group,counts,depth):
            src=x["texts"];rank=x["rank"];s={}
            for a,k in [("fixed",f),("budget",d)]:
                text="\n\n".join(trim(src[i],64)[0] for i in rank[:k])
                s[a]=[text,len(tok.encode(text,add_special_tokens=False).ids)]
            out.append({k:x[k] for k in ["id","repo","ctx","ctx_tokens","rank","file","panel","local_index"]}|dict(snippets=s,depths={"fixed":f,"budget":d},block=off//32))
    save("F_packets.json.gz",out)
    files=["F_PROTOCOL_RU.md","allocation.py","evidence.py","infer.py","A_data_lock.json","F_packets.json.gz"]
    save("F_data_lock.json",{"sha":{n:sha((D/n).read_bytes()) for n in files},"rank_model":sha((T/"budget_model.json").read_bytes()),"slots":{a:sum(x["depths"][a] for x in out) for a in ["fixed","budget"]},"changes":sum(x["depths"]["fixed"]!=x["depths"]["budget"] for x in out)})
    print(read("F_data_lock.json"),flush=True)
if __name__=="__main__":main()

