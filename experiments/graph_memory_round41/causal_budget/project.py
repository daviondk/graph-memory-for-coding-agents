"""Reconstruct only available graph structure and within-role ranks at each observation cut."""
import os
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
import gzip
import hashlib
import json
from pathlib import Path
import sys
from collections import defaultdict
D=Path(__file__).resolve().parent
W=D.parents[1]
PRE=W/"graph_memory_round22/prefix_read"
sys.path.insert(0,str(PRE))
import forecast as old
from scipy.stats import rankdata
import numpy as np
from graph_memory.datasets.isetrace.adapter import adapt_isetrace_record,parse_isetrace_record


def read(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    temp=p.with_suffix(p.suffix+".new")
    temp.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
    os.replace(temp,p)


def graph_logits(ids,indices,geometry,attrs,weights):
    names=list(ids)
    n=len(indices);members=geometry.membership
    sizes=np.bincount(members)[members]
    deg=old.packed_stats(geometry,np.zeros(n))[:,:,0]
    raw=[]
    for i,j in enumerate(indices):
        node=attrs[names[j]];m=node["attributes"];pos=m["chunk_index"];k=sizes[i]
        raw.append([int(node["kind"]=="content.tool_output"),np.log1p(m["token_count"]),np.log1p(pos),
                pos/max(1,k-1),int(pos==0),int(pos==k-1),np.log1p(k)])
    x=np.column_stack([raw,np.log1p(deg)])
    rel=np.empty((n,8))
    for role in (0,1):
        group=np.flatnonzero(x[:,0]==role)
        if len(group):rel[group]=(rankdata(x[group,7:],axis=0,method="average")-.5)/len(group)-.5
    logits=np.column_stack([x,rel])@weights["coef"]+weights["intercept"]
    return logits


def run(shards):
    weights=read(W/"graph_memory_round33/relative_structure/weights.json")["models"]["global_role"]
    idx=old.ref.graph_index()
    priors=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"]
    original={r["q"]:r for r in read(Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz"))}
    lock=read(PRE/"forecast-lock.json")
    checks={r["path"]:r["sha256"] for r in read(old.env.R18/"isetrace_official/source-lock.json")}
    for shard in shards:
        historical=PRE/f"forecast-{shard}.json.gz"
        assert sha(historical)==lock["files"][historical.name]
        frozen={(r["q"],r["cut"]):r for r in read(historical)}
        by=defaultdict(list)
        for r in read(old.ref.TR/f"forecasts-main-{shard}.json.gz"):by[r["t"]].append(r)
        source=old.env.RAW/f"trajectories-{shard:05d}.jsonl"
        assert sha(source)==checks["trajectories/"+source.name]
        rows=[];matches=0
        for rb,obj in old.env.pilot.stream(source):
            t=obj["session_id"]
            if t not in by:continue
            fp,h=idx[t]
            assert sha(fp)==h
            rec=read(fp)
            assert hashlib.sha256(rb).hexdigest()==rec["raw_source"]
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=old.env.pilot.RAW[1])
            ids,g=old.geometry(rec)
            first,groups=old.lookup(tr,rec,ids,g)
            cuts=old.cuts_for(tr.events)
            live=old.FeedIndex()
            attrs={a["node_id"]:a for a in rec["g"]["nodes"] if a["node_id"] in ids}
            for step,event in enumerate(tr.events):
                live.consume(event)
                if step not in cuts:continue
                ix=np.flatnonzero(first<=step)
                local,states=old.truncate(g,ix,live,groups)
                logits=graph_logits(ids,ix,states["exact"],attrs,weights)
                for r in by[t]:
                    q=r["q"];rr=r["rr"]
                    available=[j for j,node in enumerate(rr) if first[ids[node["node_id"]]]<=step]
                    scores=logits[[local[ids[rr[j]["node_id"]]] for j in available]]
                    if step==cuts[-1]:
                        n=len(available);v=np.arange(1,n+1)
                        rank=np.column_stack([-np.log(v),1/v,(n-v)/max(1,n-1)])@priors["coef"]+priors["intercept"]
                        assert np.allclose(scores,np.asarray(original[q]["o"])-rank,rtol=0,atol=1e-12),q
                        matches+=1
                    for cut,tick in zip((25,50,75,100),cuts):
                        if step!=tick:continue
                        prev=frozen[q,cut];assert prev["available"]==available
                        rows.append([q,t,cut,step,available,scores.tolist(),prev["pilot"]])
        assert len(rows)==len(frozen)
        name=D/f"state-{shard}.json.gz"
        write(name,rows)
        write(D/f"state-{shard}-seal.json",dict(data=sha(name),n=len(rows),terminal=matches,code=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md"),prior=sha(historical)))
        print("prefixes",shard,len(rows),"terminal matches",matches,flush=True)


if __name__=="__main__":run([int(s) for s in sys.argv[1:]] or range(8))

