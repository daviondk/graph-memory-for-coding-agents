"""Offline audit using original signed ranks, signed fine blocks and gold, with standard-library interval arithmetic."""
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

D=Path(__file__).resolve().parent;R18=D.parents[1]/"graph_memory_round18";E5=R18/"isetrace_e5";FT=D.parent/"trained_rank";OW=D.parent/"online_write";OFF=R18/"isetrace_official"
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def union(spans):
    bins=defaultdict(list)
    for e,p,a,b in spans:bins[e,p].append((a,b))
    result={}
    for k,l in bins.items():
        merged=[]
        for a,b in sorted(l):
            if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
            else:merged.append((a,b))
        result[k]=merged
    return result
def score(gold,rows):
    retrieved=union(rows);gc=sum(b-a for seg in gold.values() for a,b in seg)
    clipped=sum(max(0,min(b,y)-max(a,x)) for k,seg in gold.items() for a,b in seg for x,y in retrieved.get(k,[]))
    raw=sum(b-a for e,p,a,b in rows)
    return int(clipped==gc),clipped/gc,clipped/raw if raw else 0
def audit(model):
    src=E5 if model=="frozen" else FT;source=read(D/(model+"-source.json"));seal=read(D/(model+"-forecast-lock.json"))
    assert sha(D/(model+"-source.json"))==seal["source"] and source["model_seal"]==sha(src/"forecast-seal.json")
    truth=read(OFF/"gold-spans.json.gz");gold={q:union([(v["event_id"],v["json_pointer"],v["char_start"],v["char_end"]) for v in spans]) for q,spans in truth.items()}
    result=read(D/(model+"-outcomes.json.gz"));summary=read(D/(model+"-results.json"));seen=set()
    for i in range(8):
        rn=f"forecasts-main-{i}.json.gz";bn=f"forecast-{i}.jsonl.gz";sel=f"{model}-picks-{i}.json.gz"
        for path,h in ((src/rn,source["ranks"][rn]),(OW/bn,source["blocks"][bn]),(D/sel,seal["predictions"][sel])):assert sha(path)==h
        original={row["q"]:row for row in read(src/rn)}
        selected=read(D/sel)
        with gzip.open(OW/bn,"rb") as f:
            for rec,line in zip(selected,f,strict=True):
                stream=json.loads(line);assert rec["t"]==stream["t"] and rec["addresses"]==stream["addresses"];addr=rec["addresses"]
                for q,v in rec["q"].items():
                    assert q not in seen;seen.add(q);rank=original[q];look={r["node_id"]:r for r in rank["rr"]}
                    def values(k):
                        real=look[k];s=real["source_spans"][0];e,a,b,c=rec["nodes"][k]
                        assert real["token_count"]==c and (addr[e][0],addr[e][1],a,b)==(s["event_id"],s["json_pointer"],s["char_start"],s["char_end"])
                        return e,a,b,c
                    assert v["prefix"]==rank["arms"]["prefix"] and v["related"]==rank["arms"]["related"]
                    assert v["core"]==v["related"][:len(v["core"])]
                    base=[values(k) for k in v["core"]]
                    footprint=defaultdict(list)
                    for e,a,b,_ in base:footprint[e].append((a,b))
                    for p in ("a","b","c","prefix","related","core"):
                        if p in ("prefix","related","core"):nodes=[values(k) for k in v[p]]
                        else:
                            fine=v["fine"][p];assert len(fine)==len(set(fine))
                            free=defaultdict(list);nodes=list(base)
                            for ix in fine:
                                chunk=rec["fine"][str(ix)]
                                assert chunk==stream["blocks"][ix][:4];e,a,b,c=chunk
                                assert all(b<=l or a>=h for l,h in footprint[e]) and all(b<=l or a>=h for l,h in free[e])
                                assert any(z["source_spans"][0]["event_id"]==addr[e][0] and z["source_spans"][0]["json_pointer"]==addr[e][1] and z["source_spans"][0]["char_start"]<=a<=b<=z["source_spans"][0]["char_end"] for z in look.values())
                                free[e].append((a,b));nodes.append(chunk)
                        used=sum(z[3] for z in nodes);assert used<=2048
                        m=score(gold[q],[(*addr[e],a,b) for e,a,b,c in nodes])
                        sample=result[q][p];assert used==sample["tokens"]
                        for field,val in zip(("full_support","coverage","density"),m):assert abs(val-sample[field])<1e-12
    assert seen==set(truth)==set(result) and len(result)==2000
    for p,m in summary["stats"].items():
        assert sum(v[p]["full_support"] for v in result.values())==m["full"]
        for field in ("coverage","density","f1","tokens"):assert abs(mean(v[p][field] for v in result.values())-m[field])<1e-12
    print(model,"verified 12,000 outcomes; native trajectory/PU identity, signed 64-token chunks, containment and non-overlap")
if __name__=="__main__":
    for name in sys.argv[1:] or ("frozen","trained"):audit(name)
    if (D/"MANIFEST_SHA256.json").exists():
        for f,h in read(D/"MANIFEST_SHA256.json").items():assert sha(D/f)==h
