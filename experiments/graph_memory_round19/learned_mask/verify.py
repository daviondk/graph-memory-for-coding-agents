"""Verify the decomposition with an independent linear source-coordinate coverage calculation."""
from collections import defaultdict
from pathlib import Path
import gzip
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parent;ONLINE=ROOT.parent/"online_write";DEV=ROOT.parent/"write_transfer";LEARN=ROOT.parent/"write_learned"
OFF=ROOT.parents[1]/"graph_memory_round18/isetrace_official"
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def man():return {p.name:digest(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}
def gold_ranges(ss):
    d=defaultdict(list)
    for s in sorted(ss,key=lambda s:(s["event_id"],s["json_pointer"],s["char_start"],s["char_end"])):
        a,b=s["char_start"],s["char_end"];ranges=d[s["event_id"],s["json_pointer"]]
        if ranges and ranges[-1][1]>=a:ranges[-1][1]=max(ranges[-1][1],b)
        else:ranges.append([a,b])
    return d
def main():
    seal=load(ROOT/"forecast-seal.json");assert seal["design"]==digest(ROOT/"design.json")
    for n,h in seal["forecasts"].items():assert digest(ROOT/n)==h
    assert all(digest(ROOT.parent/p)==h for p,h in load(ROOT/"design.json").items())
    outcomes={(r["split"],r["q"]):r for r in load(ROOT/"outcomes.json.gz")}
    sums={};checked=0
    for split in ("test","dev"):
        gold=load(OFF/"gold-spans.json.gz" if split=="test" else DEV/"gold-spans.json.gz")
        diff_sets=0;diff_order=0
        for i in range(8):
            bp=(ONLINE/f"forecast-{i}.jsonl.gz") if split=="test" else (DEV/f"predictions-{i}.jsonl.gz")
            lp=LEARN/(f"forecast-{i}.jsonl.gz" if split=="test" else f"transfer-dev-{i}.jsonl.gz")
            with gzip.open(bp) as u,gzip.open(lp) as x,gzip.open(ROOT/f"prediction-{split}-{i}.jsonl.gz") as v:
                for ll,lm,lr in zip(u,x,v,strict=True):
                    raw,full,mid=map(json.loads,(ll,lm,lr));assert raw["t"]==full["t"]==mid["t"]
                    kept=set(full["a"]["tokens/full"][0])
                    for q,b in mid["B"].items():
                        a=raw["arms"]["all"][1][q];c=full["a"]["tokens/full"][1][q]
                        diff_sets+=set(c)!=set(b);diff_order+=c!=b
                        assert set(b)<=kept and set(c)<=kept
                        rr=gold_ranges(gold[q]);size=sum(e-s for arr in rr.values() for s,e in arr)
                        cover={}
                        for label,ids in (("A",a),("B",b),("C",c)):
                            touched=0;tokens=0
                            for j in ids:
                                eid,lo,hi,n,nb=raw["blocks"][j];tokens+=n
                                for left,right in rr.get(tuple(raw["addresses"][eid]),[]):
                                    touched+=max(0,min(hi,right)-max(lo,left))
                            obs=outcomes[split,q]["a"][label]
                            assert tokens==obs[3]<=2048 and touched<=size
                            assert float(touched==size)==obs[0] and abs(touched/size-obs[1])<1e-12
                            cover[label]=touched;checked+=2
                        assert cover["C"]-cover["A"]==(cover["B"]-cover["A"])+(cover["C"]-cover["B"])
        sums[split]={"B_C_different_membership":diff_sets,"B_C_different_ordered_sequence":diff_order}
    if "--write-manifest" in sys.argv:
        (ROOT/"selection-differences.json").write_text(json.dumps(sums,sort_keys=True,indent=2),encoding="utf8")
        (ROOT/"MANIFEST_SHA256.json").write_text(json.dumps(man(),sort_keys=True,indent=2),encoding="utf8")
    assert load(ROOT/"MANIFEST_SHA256.json")==man() and load(ROOT/"selection-differences.json")==sums
    print("verified",checked,"FS/coverage values, all 2580 per-query decompositions;",sums)
if __name__=="__main__":main()
