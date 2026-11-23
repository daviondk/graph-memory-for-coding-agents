"""Portable independent verifier; Python stdlib, archived IDs, disjoint offsets and official gold."""
import collections
import gzip
import hashlib
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
GOLD=HERE.parent.parent/"graph_memory_round18/isetrace_official/gold-spans.json.gz"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.name.endswith(".gz") else b)

def intervals(gold):
    keyed=collections.defaultdict(list)
    for s in gold:
        keyed[(s["event_id"],s["json_pointer"])].append((s["char_start"],s["char_end"]))
    grouped={}
    for k,v in keyed.items():
        out=[]
        for a,b in sorted(v):
            if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(b,out[-1][1]))
            else:out.append((a,b))
        grouped[k]=out
    return grouped

def close(numbers,expected):
    assert len(numbers)==len(expected) and all(math.isclose(x,y,rel_tol=0,abs_tol=1e-11) for x,y in zip(numbers,expected))

def verify():
    results=load(HERE/"results.json")
    assert sha(GOLD)==results["gold_sha256"]
    gold={q:intervals(g) for q,g in load(GOLD).items()}
    manifest=HERE/"MANIFEST_SHA256.json"
    if manifest.exists():
        assert all(sha(HERE/f)==h for f,h in load(manifest).items())
    files={"stock":"outcomes","graph":"graph-outcomes","bytes":"bytes-outcomes","mask":"mask-outcomes"}
    byfile={nm:{r["q"]:r["a"] for r in load(HERE/(f+".json.gz"))} for nm,f in files.items()}
    assert all(set(d)==set(gold) for d in byfile.values())
    seal=load(HERE/"forecast-lock.json")
    assert seal["predict"]==sha(HERE/"predict.py") and seal["protocol"]==sha(HERE/"PROTOCOL_RU.md")
    n=0
    for i in range(8):
        sources=[HERE/f"{family}-{i}.jsonl.gz" for family in ("forecast","graph","bytes","mask")]
        assert sha(sources[0])==seal["forecasts"][sources[0].name]
        assert sha(sources[1])==load(HERE/"graph-lock.json")["forecasts"][sources[1].name]
        assert sha(sources[2])==load(HERE/"bytes-lock.json")["forecasts"][i]
        assert sha(sources[3])==load(HERE/"mask-lock.json")["hashes"][i]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for lines in zip(*(stack.enter_context(gzip.open(p)) for p in sources),strict=True):
                r,g,bm,mask=map(json.loads,lines)
                assert r["t"]==g["t"]==bm["t"]==mask["t"]
                addresses=list(map(tuple,r["addresses"]))
                blocks=r["blocks"]
                # Disjointness permits adding intersections across fragments.
                last={}
                for e,a,b,wp,_ in blocks:
                    assert last.get(e,0)<=a<b and wp>0
                    last[e]=b
                for q in r["arms"]["all"][1]:
                    gt=gold[q]
                    size=sum(end-start for segs in gt.values() for start,end in segs)
                    hit=[sum(max(0,min(b,y)-max(a,x)) for x,y in gt.get(addresses[e],())) for e,a,b,_,_ in blocks]
                    def measure(ids):
                        covered=sum(hit[j] for j in ids)
                        chars=sum(blocks[j][2]-blocks[j][1] for j in ids)
                        return [int(covered==size),covered/size,covered/chars if chars else 0.]
                    for family,arms in (("stock",r["arms"]),("graph",g["arms"]),("bytes",bm["arms"])):
                        for k,entry in arms.items():
                            keep,reads=entry[:2]
                            if keep is None:keep=range(len(blocks))
                            sel=reads[q]
                            total=sum(blocks[j][3] for j in sel)
                            assert total<=2048 and len(sel)==len(set(sel)) and set(sel)<=set(keep)
                            if family!="bytes" and k!="all":
                                budget=int(k.split("/")[-1]) if family=="stock" else 8192
                                assert sum(blocks[j][3] for j in keep)<=budget
                            val=measure(keep)+measure(sel)
                            if family=="stock":val.append(total)
                            if family=="bytes":
                                ev={blocks[j][0] for j in keep}
                                sz=sum(28+blocks[j][4] for j in keep)+sum(12+sum(len(v.encode()) for v in addresses[e]) for e in ev)
                                assert entry[2]==sz<=32768
                                val.append(sz)
                            close(val,byfile[family][q][k]);n+=1
                    for k,sel in mask["q"][q].items():
                        close(measure(sel),byfile["mask"][q]["B_"+k]);n+=1
    for k,v in results["summary"].items():
        close([statistics.mean(row[k][j] for row in byfile["stock"].values()) for j in range(7)], v["metrics"])
    assert n==2000*(16+2+3+2)
    print(f"Verified {n} combinations against source coordinates for {len(gold)} queries.")
if __name__=="__main__":
    verify()

