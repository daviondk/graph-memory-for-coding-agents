"""Frozen-rank projection of learned memory; verify full- and local-corpus endpoints."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean
import gzip
import hashlib
import json
import os
import sys
ROOT=Path(__file__).resolve().parent;LEARN=ROOT.parent/"write_learned";ONLINE=ROOT.parent/"online_write";DEV=ROOT.parent/"write_transfer"
os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
sys.path.insert(0,str(ONLINE))
import predict as sw
from read_diagnostic import pack
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(name,data):
    b=json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()+b"\n";p=ROOT/name
    if p.suffix==".gz":b=gzip.compress(b,mtime=0)
    p.write_bytes(b)
def inputs(phase,i):
    if phase=="test":return ONLINE/f"forecast-{i}.jsonl.gz",LEARN/f"forecast-{i}.jsonl.gz",sw.CACHE
    return DEV/f"predictions-{i}.jsonl.gz",LEARN/f"transfer-dev-{i}.jsonl.gz",sw.RUNTIME/"write-dev-private/projection"
def locks():
    a=load(ONLINE/"forecast-lock.json");b=load(DEV/"forecast-lock.json");c=load(LEARN/"forecast-seal.json");d=load(LEARN/"transfer-forecast-seal.json")
    for root,se in ((ONLINE,a),(DEV,b),(LEARN,c),(LEARN,d)):
        for f,h in se["forecasts"].items():assert sw.digest(root/f)==h
    return {str(p.relative_to(ROOT.parent)):sw.digest(p) for p in (LEARN/"MANIFEST_SHA256.json",LEARN/"forecast-seal.json",LEARN/"transfer-forecast-seal.json",LEARN/"model.json",ONLINE/"predict.py",ONLINE/"read_diagnostic.py",ONLINE/"forecast-lock.json",DEV/"forecast-lock.json",DEV/"projection-lock.json",ROOT/"PROTOCOL_RU.md",Path(__file__))}
def lock():save("design.json",locks())
def work(key):
    phase,i=key
    bp,lp,path=inputs(phase,i);output=ROOT/f"prediction-{phase}-{i}.jsonl.gz"
    with gzip.open(bp) as base,gzip.open(lp) as learned,gzip.open(output,"wt",compresslevel=3,encoding="utf8") as dst:
        for lo,ln in zip(base,learned,strict=True):
            o,l=map(json.loads,(lo,ln));t=o["t"];assert t==l["t"]
            data=load(path/f"{i}-{t}.json.gz")
            costs=[b[3] for b in o["blocks"]]
            lex=[sw.content_tokens(data["fields"][o["addresses"][e][0]][a:b]) for e,a,b,_,_ in o["blocks"]]
            keep,saved,_=l["a"]["tokens/full"];mask=set(keep)
            assert len(keep)==len(mask) and sum(costs[j] for j in keep)<=8192
            model=sw.BM25Okapi(lex) if any(lex) else None
            questions=[(q,sw.content_tokens(txt)) for q,txt in data["q"]]
            current=sw.read(keep,costs,lex,questions)
            assert current==saved
            local={}
            for q,qt in questions:
                scores=model.get_scores(qt) if model else [0.]*len(lex)
                order=sorted(range(len(lex)),key=lambda j:(-scores[j],j))
                assert pack(order,costs)==o["arms"]["all"][1][q]
                B=pack(order,costs,mask)
                assert set(B)<=mask and sum(costs[j] for j in B)<=2048
                local[q]=B
            dst.write(sw.dump({"t":t,"B":local})+"\n")
    return output.name,sw.digest(output)
def predict():
    assert locks()==load(ROOT/"design.json")
    keyhash=hashlib.sha256()
    for p in sorted(sw.CACHE.glob("*.json.gz")):keyhash.update(p.name.encode()+b"\0"+bytes.fromhex(sw.digest(p)))
    assert keyhash.hexdigest()==load(ONLINE/"forecast-lock.json")["projection"]
    dev=load(DEV/"projection-lock.json")
    for t,v in dev["trajectories"].items():assert sw.digest(inputs("dev",v["shard"])[2]/f"{v['shard']}-{t}.json.gz")==v["projection_sha256"]
    with ProcessPoolExecutor(3) as pool:files=dict(pool.map(work,[(phase,i) for phase in ("test","dev") for i in range(8)]))
    save("forecast-seal.json",{"design":sw.digest(ROOT/"design.json"),"forecasts":files})
    print("sealed",len(files),flush=True)
def grade():
    from score import take,ci,SourceSpan,RankedNodeRecord,GOLD
    se=load(ROOT/"forecast-seal.json");assert se["design"]==sw.digest(ROOT/"design.json") and all(sw.digest(ROOT/n)==h for n,h in se["forecasts"].items())
    rowsall=[];out={}
    checkprev={(r["split"],r["q"]):r["a"]["tokens/full"] for r in load(LEARN/"transfer-outcomes.json.gz")}
    for phase in ("test","dev"):
        truth={q:tuple(SourceSpan(**s) for s in spans) for q,spans in load(GOLD if phase=="test" else DEV/"gold-spans.json.gz").items()}
        base_out={r["q"]:r["a"]["all"] for r in load((ONLINE if phase=="test" else DEV)/"outcomes.json.gz")}
        rows=[]
        for i in range(8):
            bp,lp,_=inputs(phase,i)
            with gzip.open(bp) as f,gzip.open(lp) as g,gzip.open(ROOT/f"prediction-{phase}-{i}.jsonl.gz") as h:
                for lo,lc,lb in zip(f,g,h,strict=True):
                    o,c,b=map(json.loads,(lo,lc,lb));t=o["t"];assert t==c["t"]==b["t"]
                    nodes=[]
                    for j,(ev,l,r,n,_) in enumerate(o["blocks"]):
                        eid,ptr=o["addresses"][ev]
                        nodes.append(RankedNodeRecord(node_id=str(j),score=0,token_count=n,source_spans=(SourceSpan(event_id=eid,json_pointer=ptr,char_start=l,char_end=r),)))
                    for q,B in b["B"].items():
                        sets={"A":o["arms"]["all"][1][q],"B":B,"C":c["a"]["tokens/full"][1][q]}
                        obs={}
                        for k,ids in sets.items():
                            assert len(ids)==len(set(ids))
                            selected=[nodes[j] for j in ids];tok=sum(n.token_count for n in selected);assert tok<=2048
                            obs[k]=take(selected,truth[q],True)+[tok]
                        assert obs["A"]==base_out[q][3:7] and obs["C"]==checkprev[phase,q][3:7]
                        assert abs((obs["C"][1]-obs["A"][1])-((obs["C"][1]-obs["B"][1])+(obs["B"][1]-obs["A"][1])))<1e-12
                        rows.append({"split":phase,"t":t,"q":q,"a":obs})
        assert len(rows)==len(truth) and {r["q"] for r in rows}==set(truth)
        tables={k:{"FS":sum(row["a"][k][0] for row in rows),"coverage":mean(row["a"][k][1] for row in rows),"tokens":mean(row["a"][k][3] for row in rows)} for k in ("A","B","C")}
        pairs={}
        for a,b in (("C","A"),("B","A"),("C","B")):
            pairs[a+"-"+b]={}
            for j,label in enumerate(("FS","coverage")):
                changes=[r["a"][a][j]-r["a"][b][j] for r in rows]
                pairs[a+"-"+b][label]={"ci":ci(rows,(a,b),j),"wins":sum(x>0 for x in changes),"losses":sum(x<0 for x in changes)}
        out[phase]={"n":len(rows),"trajectories":len({r["t"] for r in rows}),"arms":tables,"contrasts":pairs}
        rowsall.extend(rows);print(phase,tables,flush=True)
    save("outcomes.json.gz",rowsall);save("results.json",out)
if __name__=="__main__":{"lock":lock,"predict":predict,"score":grade}[sys.argv[1]]()
