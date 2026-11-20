"""Recreate all three exact prior agent checkpoints. Keep requests and answers in separate streams."""
import base64
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

D = Path(__file__).resolve().parent
R3 = D.parents[1]/"graph_memory_round3"
sys.path.insert(0,str(R3/"serialized_writer"))
import writer as w
from common import printed,rel

ARMS=("lru","point","typed")
DATA={"A":R3/"real_swe","B":R3/"real_swe_followup"}
def checksum(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(fp,row):fp.write(json.dumps(row,ensure_ascii=True,separators=(",",":"))+"\n")
def file(path):return gzip.open(path,"wt",encoding="utf8",compresslevel=3)

def one(job):
    panel,shard=job
    src=DATA[panel];counts=Counter()
    records=w.rows(src/f"events_{shard}.jsonl.gz")
    ws=w.read(w.R2/"span_memory/width_model.json")
    weights=(w.read(w.R2/"edit_memory/model.json")["flat"],ws,w.read(w.R2/"span_memory/offset.json")["intercept"])
    with file(D/f"input_{panel}_{shard}.jsonl.gz") as inputs, file(D/f"answer_{panel}_{shard}.jsonl.gz") as answers:
        for obj in w.rows(src/f"source_{shard}.jsonl.gz"):
            iid=obj["instance"]; rr=json.loads((D/"ranges"/(iid+".json")).read_bytes())
            blobs={a:w.empty(a) for a in ARMS}
            static={"instance":iid,"issue":obj["issue"]}
            for t,event in enumerate(obj["events"],1):
                id0,t0,hist=next(records);assert (id0,t0)==(iid,t)
                expected={a:h for a,b,h,*_ in hist if b==4096 and a in ARMS}
                _,args,obs=event;path=rel(args.get("path"))
                if args.get("command")=="view" and path:
                    counts["path_views"]+=1
                    lines=printed(obs)
                    if not lines:counts["empty_or_unpaired_view"]+=1
                    elif rr["status"]!="ok":counts["missing_native_range"]+=1
                    else:
                        vr=rr["ranges"][str(t)]
                        valid=(vr is None or (isinstance(vr,list) and len(vr)==2 and all(type(x) is int for x in vr) and vr[0]>=1 and (vr[1]>=vr[0] or vr[1]==-1)))
                        if not valid:counts["invalid_range"]+=1
                        else:
                            counts["views"]+=1
                            # The current result is written to the scorer only. Query input includes the previous bytes.
                            put(inputs,[iid,obj["official_repo"],t,path,vr,{a:base64.b64encode(blobs[a]).decode() for a in ARMS}])
                            put(answers,[iid,t,sorted(lines.items())])
                for a in ARMS:
                    blobs[a],_=w.transition(blobs[a],event,static,weights,4096)
                    assert w.h(blobs[a])==expected[a] and len(blobs[a])<=4096
                    counts["identical_historical_checkpoints"]+=1
            counts["issues"]+=1
    assert next(records,None) is None
    return panel,dict(counts)

def main():
    os.environ["OPENBLAS_NUM_THREADS"]="1"
    with ProcessPoolExecutor(4) as pool:
        result=list(pool.map(one,[(panel,k) for panel in DATA for k in range(8)]))
    out={}
    for panel,counts in result:
        out.setdefault(panel,Counter()).update(counts)
    (D/"panel_counts.json").write_text(json.dumps(out,indent=2),encoding="utf8")
    print(out,flush=True)

if __name__=="__main__":main()
