"""Decompose effects of masking full-corpus BM25 ranks and refitting BM25."""
import sys
import collections
import gzip
import json
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from predict import HERE,CACHE,BM25Okapi,content_tokens,dump,digest

def pack(order,cost,mask=None):
    remain=2048
    keep=[]
    for i in order:
        if (mask is None or i in mask) and cost[i]<=remain:
            keep.append(i)
            remain-=cost[i]
            if remain==0:break
    return keep

def work(shard):
    file=HERE/f"mask-{shard}.jsonl.gz"
    with gzip.open(HERE/f"forecast-{shard}.jsonl.gz","rb") as f,gzip.open(file,"wt",encoding="utf-8",compresslevel=3) as w:
        for line in f:
            r=json.loads(line)
            with gzip.open(CACHE/f"{shard}-{r['t']}.json.gz") as x: raw=json.load(x)
            blocks=r["blocks"]
            corpus=[content_tokens(raw["fields"][r["addresses"][e][0]][a:b]) for e,a,b,_,_ in blocks]
            bm=BM25Okapi(corpus) if any(corpus) else None
            costs=[b[3] for b in blocks]
            qs={}
            for q,txt in raw["q"]:
                scores=bm.get_scores(content_tokens(txt)) if bm else [0.]*len(blocks)
                order=sorted(range(len(scores)),key=lambda i:(-scores[i],i))
                assert pack(order,costs)==r["arms"]["all"][1][q]
                qs[q]={k:pack(order,costs,set(r["arms"][k+"/8192"][0])) for k in ("fifo","output_head")}
            w.write(dump(dict(t=r["t"],q=qs))+"\n")
    return digest(file)

def predict():
    lock=json.loads((HERE/"forecast-lock.json").read_bytes())
    assert all(digest(HERE/f)==h for f,h in lock["forecasts"].items())
    with ProcessPoolExecutor(4) as pool: hashes=list(pool.map(work,range(8)))
    (HERE/"mask-lock.json").write_text(dump(dict(hashes=hashes,inputs=digest(HERE/"forecast-lock.json"),
        method=digest(HERE/"read_diagnostic.py"),protocol=digest(HERE/"READER_PROTOCOL_RU.md"))),encoding="utf-8")

def score():
    from score import GOLD,SourceSpan,RankedNodeRecord,take,ci
    lock=json.loads((HERE/"mask-lock.json").read_bytes())
    assert lock["method"]==digest(HERE/"read_diagnostic.py") and lock["protocol"]==digest(HERE/"READER_PROTOCOL_RU.md")
    truth={q:tuple(SourceSpan(**x) for x in spans) for q,spans in json.load(gzip.open(GOLD,"rb")).items()}
    initial={r["q"]:r["a"] for r in json.load(gzip.open(HERE/"outcomes.json.gz","rb"))}
    rows=[]
    for i,h in enumerate(lock["hashes"]):
        file=HERE/f"mask-{i}.jsonl.gz"
        assert digest(file)==h
        with gzip.open(file) as f,gzip.open(HERE/f"forecast-{i}.jsonl.gz") as ref:
            for l,m in zip(f,ref,strict=True):
                g,r=json.loads(l),json.loads(m)
                assert g["t"]==r["t"]
                nodes=[]
                for j,(e,a,b,c,s) in enumerate(r["blocks"]):
                    eid,ptr=r["addresses"][e]
                    span=SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b)
                    nodes.append(RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(span,)))
                for q,arms in g["q"].items():
                    scores={"A":initial[q]["all"][3:6]}
                    for k,ids in arms.items():
                        assert set(ids)<=set(r["arms"][k+"/8192"][0]) and sum(nodes[j].token_count for j in ids)<=2048
                        scores["B_"+k]=take([nodes[j] for j in ids],truth[q],False)
                        scores["C_"+k]=initial[q][k+"/8192"][3:6]
                    rows.append(dict(q=q,t=g["t"],a=scores))
    assert len(rows)==2000 and {r["q"] for r in rows}==truth.keys()
    out=dict(means={k:np.mean([r["a"][k] for r in rows],axis=0).tolist() for k in rows[0]["a"]},
        contrasts={k+"/"+a+"-"+b+"/"+metric:ci(rows,(a,b),j) for k in ("fifo","output_head")
        for a,b in [("B_"+k,"A"),("C_"+k,"B_"+k),("C_"+k,"A")] for j,metric in [(0,"read_FS"),(1,"read_coverage")]})
    (HERE/"mask-outcomes.json.gz").write_bytes(gzip.compress(dump(rows).encode(),mtime=0))
    (HERE/"mask-results.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
if __name__=="__main__":
    {"predict":predict,"score":score}[sys.argv[1]]()

