"""Replay completed events in order. The writer has no access to questions or labels."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
import math
import os
from pathlib import Path
import re
import sys
for env in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[env]="1"
D=Path(__file__).resolve().parent
OLD=D.parents[1]/"graph_memory_round19"
sys.path.insert(0,str(OLD/"write_learned"))
from forecast_write import fitted_scores
from features import load, save, sha, stream, rows, tool_lookup
import numpy as np

TERM=re.compile(r"[A-Za-z0-9][A-Za-z0-9./_\\-]{4,}")
def literals(text):
    tokens=(m.group().rstrip("./_-\\").lower() for m in TERM.finditer(text))
    return tuple(dict.fromkeys(x for x in tokens if len(x)>=5 and re.search(r"[\d./_\\-]",x)))[:32]

def simulate(blocks,addresses,data,model):
    fields=data["fields"]
    x,names=rows(addresses,blocks,fields,tool_lookup(data["pool"]))
    prob=fitted_scores(x,names,model,"full")
    logit=np.log(np.clip(prob,1e-14,1-1e-14)/(1-np.clip(prob,1e-14,1-1e-14)))
    ties=[stream.stable(eid) for eid,_ in addresses]
    calls={s["event_id"]:p["metadata"].get("call_id") for p in data["pool"] for s in p["source_spans"]}
    call=[calls[eid] for eid,_ in addresses]
    output=[ptr=="/content" for _,ptr in addresses]
    results={}
    for arm in ("real","placebo"):
        active={};termlist={};inverted=defaultdict(set)
        used=0;changed=set();signals=promotions=0;peak_terms=peak_postings=peak_key_bytes=0
        postings=key_bytes=0
        for i,(e,a,b,c,_) in enumerate(blocks):
            terms=literals(fields[addresses[e][0]][a:b])
            if not output[e] and call[e] is not None:
                targets=set()
                for word in terms:
                    matches=inverted.get(word)
                    if matches and len(matches)<=2:
                        targets.update(j for j in matches if call[blocks[j][0]] is not None and call[blocks[j][0]]!=call[e])
                signals+=len(targets)
                if targets and arm=="placebo":
                    eligible=sorted(j for j in termlist if call[blocks[j][0]] is not None and call[blocks[j][0]]!=call[e])
                    shift=len(eligible)//2
                    offset={j:k for k,j in enumerate(eligible)}
                    targets={eligible[(offset[j]+shift)%len(eligible)] for j in targets}
                for j in targets-changed:
                    active[j]=(-(logit[j]+math.log(2)),ties[blocks[j][0]],j)
                    changed.add(j);promotions+=1
            active[i]=(-logit[i],ties[e],i)
            used+=c
            if output[e]:
                termlist[i]=terms
                for word in terms:
                    if word not in inverted:key_bytes+=len(word.encode())
                    inverted[word].add(i);postings+=1
            while used>8192:
                j=max(active,key=active.__getitem__);del active[j];used-=blocks[j][3]
                changed.discard(j)
                for word in termlist.pop(j,()):
                    inverted[word].remove(j);postings-=1
                    if not inverted[word]:
                        del inverted[word];key_bytes-=len(word.encode())
            peak_terms=max(peak_terms,len(inverted));peak_key_bytes=max(peak_key_bytes,key_bytes)
            peak_postings=max(peak_postings,postings)
        results[arm]=(sorted(active),[signals,promotions,peak_terms,peak_postings,peak_key_bytes])
    keys=[((-float(p),ties[b[0]]),) for b,p in zip(blocks,prob,strict=True)]
    results["frozen"]=(stream.select([b[3] for b in blocks],keys,0,8192),[0]*5)
    return results

def shard(i):
    model=load(OLD/"write_learned/model.json");out=D/f"forecast-{i}.jsonl.gz"
    with gzip.open(OLD/"online_write"/out.name,"rb") as src,gzip.open(OLD/"write_learned"/out.name,"rb") as previous,gzip.open(out,"wt",encoding="utf8",compresslevel=3) as dst:
        for line,priorline in zip(src,previous,strict=True):
            r=json.loads(line);prior=json.loads(priorline);t=r["t"];assert prior["t"]==t
            data=load(stream.CACHE/f"{i}-{t}.json.gz")
            blocks,addr=r["blocks"],r["addresses"]
            policies=simulate(blocks,addr,data,model)
            questions=[(q,stream.content_tokens(s)) for q,s in data["q"]]
            words=[stream.content_tokens(data["fields"][addr[e][0]][a:b]) for e,a,b,_,_ in blocks]
            costs=[b[3] for b in blocks];arms={}
            for arm,(keep,stats) in policies.items():
                assert sum(costs[j] for j in keep)<=8192
                picks=stream.read(keep,costs,words,questions)
                if arm=="frozen":
                    assert [keep,picks]==prior["a"]["tokens/full"][:2]
                arms[arm]=[keep,picks,stats]
            dst.write(stream.dump({"t":t,"a":arms})+"\n")
    return sha(out)
if __name__=="__main__":
    dc={"input_model":sha(OLD/"write_learned/model.json"),"source_lock":sha(OLD/"online_write/forecast-lock.json"),**{n:sha(D/n) for n in ("update.py","PROTOCOL_RU.md")}}
    save(D/"design.json",dc)
    with ProcessPoolExecutor(3) as ex:
        files=list(ex.map(shard,range(8)))
    save(D/"forecast-seal.json",{"design":sha(D/"design.json"),"files":{f"forecast-{i}.jsonl.gz":h for i,h in enumerate(files)}})
