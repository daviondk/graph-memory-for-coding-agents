"""Open the held-out span labels after all eight forecasts have been sealed."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from statistics import mean
import sys
import numpy as np
from features import ROOT,ONLINE,load,save,sha,stream,binary
from score import GOLD,SourceSpan,RankedNodeRecord,take,ci

def measure():
    seal=load(ROOT/"forecast-seal.json");assert seal["model"]==sha(ROOT/"model-seal.json")
    assert all(sha(ROOT/n)==h for n,h in seal["forecasts"].items())
    truth={q:tuple(SourceSpan(**s) for s in spans) for q,spans in load(GOLD).items()}
    rows=[];costs=[];checked=0
    for i in range(8):
        with gzip.open(ROOT/f"forecast-{i}.jsonl.gz") as a,gzip.open(ONLINE/f"forecast-{i}.jsonl.gz") as b,gzip.open(ONLINE/f"bytes-{i}.jsonl.gz") as c:
            for la,lb,lc in zip(a,b,c,strict=True):
                r,base,binarybase=map(json.loads,(la,lb,lc));t=r["t"]
                assert t==base["t"]==binarybase["t"]
                blocks=base["blocks"];addresses=base["addresses"]
                def cost_of(ids):
                    byts=sum(blocks[k][4] for k in ids)
                    index=sum(binary.EV.size+len(addresses[e][0].encode())+len(addresses[e][1].encode()) for e in {blocks[k][0] for k in ids})
                    return {"stored_tokens":sum(blocks[k][3] for k in ids),"binary_bytes":byts+len(ids)*binary.HDR.size+index,"payload_bytes":byts}
                total=cost_of(range(len(blocks)))
                binding={"tokens":total["stored_tokens"]>8192,"bytes":total["binary_bytes"]>32768}
                for pol in ("fifo","output_head"):
                    ids,reads=base["arms"][pol+"/8192"];r["a"]["tokens/"+pol]=[ids,reads,cost_of(ids)]
                    ids,reads,bytes_=binarybase["arms"][pol];cost=cost_of(ids);assert cost["binary_bytes"]==bytes_
                    r["a"]["bytes/"+pol]=[ids,reads,cost]
                nodes=[RankedNodeRecord(node_id=str(j),score=0,token_count=price,source_spans=(SourceSpan(
                    event_id=addresses[e][0],json_pointer=addresses[e][1],char_start=l,char_end=h),)) for j,(e,l,h,price,_) in enumerate(blocks)]
                checked_here=int(hashlib.sha256(t.encode()).hexdigest()[:8],16)%16==0
                outcomes={};cost_row={}
                for arm,(ids,reads,cost) in r["a"].items():
                    assert cost==cost_of(ids);mode=arm.split("/")[0]
                    if mode=="tokens":assert cost["stored_tokens"]<=8192
                    else:assert cost["binary_bytes"]<=32768
                    if not binding[mode]:assert ids==list(range(len(blocks)))
                    left=set(ids);assert len(ids)==len(left)
                    kept=[nodes[j] for j in ids]
                    for q,chosen in reads.items():
                        assert set(chosen)<=left and len(set(chosen))==len(chosen)
                        retrieved=[nodes[j] for j in chosen];tokens=sum(n.token_count for n in retrieved)
                        assert tokens<=2048
                        w=take(kept,truth[q],checked_here);rr=take(retrieved,truth[q],checked_here)
                        assert rr[0]<=w[0] and rr[1]<=w[1]+1e-12
                        outcomes.setdefault(q,{})[arm]=w+rr+[tokens];checked+=2*checked_here
                    cost_row[arm]=cost
                for q,x in outcomes.items():
                    for mode in binding:
                        if not binding[mode]:
                            assert all(x[mode+"/"+arm]==x[mode+"/fifo"] for arm in ("positional","full","spread","output_head"))
                    rows.append({"t":t,"q":q,"a":x,"binding":binding})
                costs.append({"t":t,"c":cost_row,"binding":binding})
        print("scored",i,len(rows),flush=True)
    assert len(rows)==len(truth)==2000 and {r["q"] for r in rows}==set(truth) and len(costs)==1207
    result={"n":len(rows),"trajectories":len(costs),"independent_checks":checked,"gold_sha":sha(GOLD),"modes":{}}
    for mode in ("tokens","bytes"):
        metrics={}
        for label,rr in (("all",rows),("binding_only",[r for r in rows if r["binding"][mode]])):
            selected=costs if label=="all" else [r for r in costs if r["binding"][mode]]
            desc={};pairs={}
            for arm in ("fifo","output_head","positional","full","spread"):
                k=mode+"/"+arm;data=np.array([r["a"][k] for r in rr],dtype=float)
                desc[arm]={"write_count":int(data[:,0].sum()),"read_count":int(data[:,3].sum()),"mean":data.mean(0).tolist(),
                    "storage":{v:mean(s["c"][k][v] for s in selected) for v in ("stored_tokens","binary_bytes","payload_bytes")}}
            for a,b in (("full","output_head"),("full","fifo"),("full","positional"),("spread","full"),("spread","output_head")):
                x,y=mode+"/"+a,mode+"/"+b
                pairs[a+"-"+b]={}
                for k,field in ((0,"write_fs"),(3,"read_fs"),(4,"read_cov")):
                    ar=[r["a"][x][k]-r["a"][y][k] for r in rr]
                    pairs[a+"-"+b][field]={"diff_ci":ci(rr,(x,y),k),"wins":sum(v>0 for v in ar),"losses":sum(v<0 for v in ar)}
            metrics[label]={"n":len(rr),"trajectories":len(selected),"arms":desc,"contrasts":pairs}
        result["modes"][mode]=metrics
    save(ROOT/"outcomes.json.gz",rows);save(ROOT/"storage.json.gz",costs);save(ROOT/"results.json",result)
    print({m:{k:(v["write_count"],v["read_count"]) for k,v in d["all"]["arms"].items()} for m,d in result["modes"].items()})
if __name__=="__main__":measure()
