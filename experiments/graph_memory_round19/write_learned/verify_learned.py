"""Recompute FS directly from frozen disjoint blocks and optionally exercise the write/read API."""
from collections import defaultdict
from pathlib import Path
import gzip
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parent;ONLINE=ROOT.parent/"online_write";DEV=ROOT.parent/"write_transfer"
OFF=ROOT.parents[1]/"graph_memory_round18/isetrace_official"
def data(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def mfiles():return {p.name:digest(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}
def requirements(coords,raw,qs):
    by=defaultdict(list)
    for j,(e,a,b,_,_) in enumerate(raw["blocks"]):by[tuple(raw["addresses"][e])].append((a,b,j))
    for arr in by.values():assert all(arr[i-1][1]<=arr[i][0] for i in range(1,len(arr)))
    out={}
    for q in qs:
        needed=set();possible=True
        for s in coords[q]:
            a=s["char_start"];b=s["char_end"];coverage=0
            for u,v,j in by[s["event_id"],s["json_pointer"]]:
                overlap=min(v,b)-max(u,a)
                if overlap>0:needed.add(j);coverage+=overlap
            assert coverage<=b-a
            possible &= coverage==b-a
        out[q]=(possible,needed)
    return out
def api(stage,i,raw,arms):
    import numpy as np
    from features import stream,tool_lookup,rows,load
    from forecast_write import choose
    from transfer_write import recent_projection
    p=load(recent_projection(stage,i,raw["t"]));model=load(ROOT/"model.json")
    addr=raw["addresses"];blocks=raw["blocks"]
    # Remove future events and omit all questions entirely when computing prefix features.
    cutoff=max(1,len(addr)//2)
    head=addr[:cutoff];ev={k for k,ptr in head};items=[b for b in blocks if b[0]<cutoff]
    raw_head={k:p["fields"][k] for k in ev}
    prefix_pool=[c for c in p["pool"] if all(s["event_id"] in ev for s in c["source_spans"])]
    x,n=rows(head,items,raw_head,tool_lookup(prefix_pool))
    xx,nn=rows(addr,blocks,p["fields"],tool_lookup(p["pool"]))
    assert np.array_equal(x,xx[:len(items)]) and n==nn[:len(items)]
    local=choose(addr,blocks,p["fields"],p["pool"],model)
    for name,(keep,read,_) in arms.items():
        if name not in local:continue
        assert local[name][0]==keep
        if name!="tokens/full":continue
        # Object deliberately has no payload for evicted IDs; any attempt to read them raises.
        retained={i:stream.content_tokens(p["fields"][addr[blocks[i][0]][0]][blocks[i][1]:blocks[i][2]]) for i in keep}
        out=stream.read(keep,[b[3] for b in blocks],retained,[(q,stream.content_tokens(txt)) for q,txt in p["q"]])
        assert out==read
def main():
    if "--write-manifest" in sys.argv:(ROOT/"MANIFEST_SHA256.json").write_text(json.dumps(mfiles(),sort_keys=True,indent=2),encoding="utf8")
    assert data(ROOT/"MANIFEST_SHA256.json")==mfiles()
    model_sha=digest(ROOT/"model.json");assert model_sha==data(ROOT/"model-seal.json")["model.json"]==data(ROOT/"transfer-plan.json")["local"]["model.json"]
    assert (ROOT/"model.json").stat().st_size==3911
    tr=data(ROOT/"train-evidence.json.gz");dev=data(DEV/"cohort.json");te=data(OFF/"cohort.json")
    assert len(tr)==256 and not(set(tr)&({r["t"] for r in dev}|{r["trajectory_id"] for r in te}))
    assert not {q for t in tr.values() for q in t["q"]}&({r["q"] for r in dev}|{r["query_id"] for r in te})
    initial=data(ROOT/"forecast-seal.json");transfer=data(ROOT/"transfer-forecast-seal.json")
    assert all(digest(ROOT/n)==v for seal in (initial,transfer) for n,v in seal["forecasts"].items())
    trows={(x["split"],x["q"]):x for x in data(ROOT/"transfer-outcomes.json.gz")}
    gold={"test":data(OFF/"gold-spans.json.gz"),"dev":data(DEV/"gold-spans.json.gz")}
    checks=0;api_calls=0
    for stage,kind in (("test","initial"),("dev","transfer"),("test","transfer")):
        for i in range(8):
            base=ONLINE/f"forecast-{i}.jsonl.gz" if stage=="test" else DEV/f"predictions-{i}.jsonl.gz"
            local=ROOT/(f"forecast-{i}.jsonl.gz" if kind=="initial" else f"transfer-{stage}-{i}.jsonl.gz")
            with gzip.open(base) as source,gzip.open(local) as selected:
                for lb,lc in zip(source,selected,strict=True):
                    b,c=map(json.loads,(lb,lc));assert b["t"]==c["t"]
                    qs=next(iter(c["a"].values()))[1]
                    needed=requirements(gold[stage],b,qs)
                    if "--api-check" in sys.argv and kind!="transfer" or "--api-check" in sys.argv and stage=="dev":
                        if int(hashlib.sha256(b["t"].encode()).hexdigest()[:6],16)%53==0:
                            api(stage,i,b,c["a"]);api_calls+=1
                    for arm,(keep,reads,_) in c["a"].items():
                        ks=set(keep)
                        for q,r in reads.items():
                            possible,need=needed[q];assert set(r)<=ks
                            vals=trows[stage,q]["a"][arm]
                            assert vals[0]==bool(possible and need<=ks) and vals[3]==bool(possible and need<=set(r))
                            checks+=2
    observed=data(ROOT/"train-statistics.json")
    assert observed["n"]==145498 and observed["positive"]==844 and observed["queries"]==411
    print("OK",len(mfiles()),"files;",checks,"independently rescored write/read outcomes;",api_calls,"prefix and retained-only API checks")
if __name__=="__main__":main()
