"""Write without seeing questions; only then apply the original BM25 read implementation."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
import math
import os
import sys
os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["MKL_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
import numpy as np
from features import ROOT,ONLINE,TRAINED,stream,binary,load,save,sha,rows,design,tool_lookup

def fitted_scores(x,names,model,arm):
    m=model["arms"][arm]
    z=design(x,names,model["tools"],arm=="full")
    linear=(z-np.asarray(m["means"]))/np.asarray(m["scale"])@np.asarray(m["coefficients"])+m["intercept"]
    return 1/(1+np.exp(-np.clip(linear,-700,700)))
def choose(addresses,blocks,fields,sourcepool,model):
    x,names=rows(addresses,blocks,fields,tool_lookup(sourcepool))
    scores={k:fitted_scores(x,names,model,k) for k in ("full","positional")}
    events=defaultdict(list)
    for i,b in enumerate(blocks):events[b[0]].append(i)
    spread=scores["full"].copy()
    for seq in events.values():
        for j,i in enumerate(sorted(seq,key=lambda i:(-scores["full"][i],i))):spread[i]/=math.sqrt(1+j)
    scores["spread"]=spread
    cost=[b[3] for b in blocks];es=[]
    for j,(eid,ptr) in enumerate(addresses):
        a,b=eid.encode(),ptr.encode();es.append(binary.EV.pack(j,len(a),len(b))+a+b)
    ties=[stream.stable(eid) for eid,_ in addresses]
    ans={}
    for arm,vals in scores.items():
        prio=[(-float(s),ties[b[0]]) for b,s in zip(blocks,vals,strict=True)]
        keep=stream.select(cost,[(key,) for key in prio],0,8192)
        kb,used=binary.select(blocks,prio,es)
        assert sum(cost[i] for i in keep)<=8192
        assert sum(binary.HDR.size+blocks[i][4] for i in kb)+sum(len(es[e]) for e in {blocks[i][0] for i in kb})==used<=32768
        ans["tokens/"+arm]=[keep,None];ans["bytes/"+arm]=[kb,used]
    return ans
def shard(i):
    model=load(ROOT/"model.json")
    out=ROOT/f"forecast-{i}.jsonl.gz"
    with gzip.open(ONLINE/f"forecast-{i}.jsonl.gz","rt",encoding="utf8") as fixed,gzip.open(ONLINE/f"bytes-{i}.jsonl.gz","rt",encoding="utf8") as byte, gzip.open(out,"wt",encoding="utf8",compresslevel=3) as dst:
        for raw,byte_line in zip(fixed,byte,strict=True):
            base=json.loads(raw);tid=base["t"];frozen=json.loads(byte_line);assert tid==frozen["t"]
            proj=load(stream.CACHE/f"{i}-{tid}.json.gz");assert proj["t"]==tid
            ad,blocks=base["addresses"],base["blocks"];fields=proj["fields"]
            retained=choose(ad,blocks,fields,proj["pool"],model)
            questions=[(qid,stream.content_tokens(txt)) for qid,txt in proj["q"]]
            lex=[stream.content_tokens(fields[ad[e][0]][a:b]) for e,a,b,_,_ in blocks];cost=[b[3] for b in blocks]
            out_arms={}
            for k,(indices,used) in retained.items():
                selected=stream.read(indices,cost,lex,questions)
                meta=[[blocks[j][0],blocks[j][1],blocks[j][2]] for j in indices]
                address_map={e:ad[e] for e in sorted({b[0] for b in meta})}
                binary_bytes=sum(blocks[j][4]+binary.HDR.size for j in indices)+sum(binary.EV.size+len(a.encode())+len(b.encode()) for a,b in address_map.values())
                if used is not None:assert binary_bytes==used
                out_arms[k]=[indices,selected,{"stored_tokens":sum(cost[j] for j in indices),"binary_bytes":binary_bytes,
                        "payload_bytes":sum(blocks[j][4] for j in indices)}]
            dst.write(stream.dump({"t":tid,"a":out_arms})+"\n")
    print("sealed source-only shard",i,flush=True)
    return sha(out)
def main():
    sealed=load(ROOT/"model-seal.json");assert all(sha(ROOT/n)==h for n,h in sealed.items())
    lock=load(ROOT/"plan.json");lookup={n:ROOT/n for n in ("PROTOCOL_RU.md","features.py","train_write.py","forecast_write.py")}
    lookup.update({n:ONLINE/n for n in ("predict.py","byte_memory.py","forecast-lock.json","bytes-lock.json")});lookup["split.json.gz"]=TRAINED/"split.json.gz"
    assert all(sha(lookup[k])==v for k,v in lock["inputs"].items())
    a=load(ONLINE/"forecast-lock.json");b=load(ONLINE/"bytes-lock.json")
    assert all(sha(ONLINE/n)==v for n,v in a["forecasts"].items())
    assert all(sha(ONLINE/f"bytes-{i}.jsonl.gz")==h for i,h in enumerate(b["forecasts"]))
    import hashlib
    dig=hashlib.sha256()
    for f in sorted(stream.CACHE.glob("*.json.gz")):dig.update(f.name.encode()+b"\0"+bytes.fromhex(sha(f)))
    assert dig.hexdigest()==a["projection"]
    with ProcessPoolExecutor(max_workers=3) as p:hashes=list(p.map(shard,range(8)))
    save(ROOT/"forecast-seal.json",{"model":sha(ROOT/"model-seal.json"),"forecasts":{f"forecast-{i}.jsonl.gz":v for i,v in enumerate(hashes)}})
if __name__=="__main__":main()
