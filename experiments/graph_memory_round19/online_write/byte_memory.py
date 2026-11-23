"""Byte-constrained streaming admission including address table; serializer audits final states."""
import collections
import gzip
import heapq
import json
import struct
import sys
from concurrent.futures import ProcessPoolExecutor
from predict import HERE,CACHE,content_tokens,digest,dump,read,stable

CAP = 32768
HDR = struct.Struct(">IQQII")
EV = struct.Struct(">III")

def select(blocks, keys, event_bytes):
    active = collections.Counter()
    heap = []
    used = 0
    for i,((e,_,_,_,b),key) in enumerate(zip(blocks,keys,strict=True)):
        if not active[e]:
            used += len(event_bytes[e])
        active[e] += 1
        used += HDR.size+b
        heapq.heappush(heap,(-key[0],-key[1],-i,i))
        while used>CAP:
            worst = heapq.heappop(heap)[3]
            ev,_,_,_,size = blocks[worst]
            used -= HDR.size+size
            active[ev] -= 1
            if not active[ev]:
                used -= len(event_bytes[ev])
    return sorted(x[3] for x in heap),used

def worker(shard):
    with gzip.open(HERE/f"forecast-{shard}.jsonl.gz","rt",encoding="utf-8") as originals, \
         gzip.open(HERE/f"bytes-{shard}.jsonl.gz","wt",encoding="utf-8",compresslevel=3) as out:
        for line in originals:
            r=json.loads(line)
            with gzip.open(CACHE/f"{shard}-{r['t']}.json.gz") as f:
                raw=json.load(f)
            addresses=r["addresses"]
            texts=[raw["fields"][eid] for eid,_ in addresses]
            blocks=r["blocks"]
            costs=[b[3] for b in blocks]
            fragments=[texts[e][a:b] for e,a,b,_,_ in blocks]
            lex=[content_tokens(v) for v in fragments]
            event_bytes=[]
            for e,(eid,ptr) in enumerate(addresses):
                x,y=eid.encode(),ptr.encode()
                event_bytes.append(EV.pack(e,len(x),len(y))+x+y)
            depths=collections.Counter()
            keys={"head":[],"fifo":[],"output_head":[]}
            for i,(e,_,_,_,_) in enumerate(blocks):
                eid,ptr=addresses[e]
                j=depths[e]
                keys["head"].append((j,stable(eid)))
                keys["output_head"].append((2*j if ptr=="/raw_arguments" else j,stable(eid)))
                keys["fifo"].append((-i,0))
                depths[e]+=1
            questions=[(q,content_tokens(txt)) for q,txt in raw["q"]]
            arms={}
            for k,key in keys.items():
                keep,used=select(blocks,key,event_bytes)
                stored_events={blocks[i][0] for i in keep}
                dictionary=b"".join(event_bytes[e] for e in sorted(stored_events))
                payload=bytearray()
                for i in keep:
                    e,a,b,c,nbyte=blocks[i]
                    x=fragments[i].encode()
                    assert len(x)==nbyte
                    payload.extend(HDR.pack(e,a,b-a,nbyte,c))
                    payload.extend(x)
                assert used==len(dictionary)+len(payload)<=CAP
                arms[k]=[keep,read(keep,costs,lex,questions),used]
            out.write(dump(dict(t=r["t"],arms=arms))+"\n")
    return digest(HERE/f"bytes-{shard}.jsonl.gz")

def predict():
    lock=json.loads((HERE/"forecast-lock.json").read_bytes())
    assert all(digest(HERE/name)==h for name,h in lock["forecasts"].items())
    with ProcessPoolExecutor(4) as p:
        hashes=list(p.map(worker,range(8)))
    (HERE/"bytes-lock.json").write_text(dump(dict(forecasts=hashes,inputs=digest(HERE/"forecast-lock.json"),
        method=digest(HERE/"byte_memory.py"),protocol=digest(HERE/"BYTE_PROTOCOL_RU.md"))),encoding="utf-8")

def score():
    import numpy as np
    from score import GOLD,SourceSpan,RankedNodeRecord,take,ci
    lock=json.loads((HERE/"bytes-lock.json").read_bytes())
    assert lock["protocol"]==digest(HERE/"BYTE_PROTOCOL_RU.md") and lock["method"]==digest(HERE/"byte_memory.py")
    truth={q:tuple(SourceSpan(**x) for x in s) for q,s in json.load(gzip.open(GOLD,"rb")).items()}
    rows=[]
    for i,h in enumerate(lock["forecasts"]):
        path=HERE/f"bytes-{i}.jsonl.gz"
        assert h==digest(path)
        with gzip.open(path) as preds,gzip.open(HERE/f"forecast-{i}.jsonl.gz") as originals:
            for l,m in zip(preds,originals,strict=True):
                g,r=json.loads(l),json.loads(m)
                assert r["t"]==g["t"]
                nodes=[]
                for j,(e,a,b,c,nbyte) in enumerate(r["blocks"]):
                    eid,ptr=r["addresses"][e]
                    s=SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b)
                    nodes.append(RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(s,)))
                scores={}
                for arm,(keep,reads,used) in g["arms"].items():
                    kept=[nodes[j] for j in keep]
                    for q,sel in reads.items():
                        assert set(sel)<=set(keep)
                        rs=[nodes[j] for j in sel]
                        assert sum(n.token_count for n in rs)<=2048
                        scores.setdefault(q,{})[arm]=take(kept,truth[q],False)+take(rs,truth[q],False)+[used]
                rows.extend(dict(t=r["t"],q=q,a=arms) for q,arms in scores.items())
    assert {x["q"] for x in rows}==truth.keys() and len(rows)==2000
    out=dict(means={a:np.mean([r["a"][a] for r in rows],axis=0).tolist() for a in ("head","fifo","output_head")},
             contrasts={f"{a}-{b}/{name}":ci(rows,(a,b),k) for a,b in [("head","fifo"),("output_head","head")]
                        for name,k in [("write_FS",0),("read_FS",3)]})
    (HERE/"bytes-outcomes.json.gz").write_bytes(gzip.compress(dump(rows).encode(),mtime=0))
    (HERE/"bytes-results.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
if __name__=="__main__":
    {"predict":predict,"score":score}[sys.argv[1]]()

