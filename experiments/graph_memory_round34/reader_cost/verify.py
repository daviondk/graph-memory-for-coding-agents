"""Independently verify physical artifacts and medians with the standard library."""
from pathlib import Path
from collections import defaultdict,Counter
import gzip,hashlib,json,math,statistics
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def close(x,y):return math.isclose(x,y,abs_tol=1e-9)
def main():
    h=get(D/"manifest.json")
    for k,v in h.items():assert sha(D/k)==v,k
    assert set(h)=={p.name for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    plan=get(D/"plan.json");replay=get(D/"replay.json.gz");summary=get(D/"summary.json"); ft=get(D/"file-summary.json")
    assert plan["protocol"]==sha(D/"PROTOCOL_RU.md") and plan["linear"]==sha(D/"linear-model.json")
    assert len(plan["panel"])==96 and {q for q,t in plan["panel"]}==replay.keys() and len({t for q,t in plan["panel"]})==94
    assert all(a["fs"]==a["reference_fs"] for r in replay.values() for a in r["arms"].values())
    d=get(D/"replay-differences.json")
    assert all(m["prefix_same_set"] and m["with_reference_dense_reconstructs_cost"] for v in d.values() for m in v.values())
    timings=get(D/"times.json.gz");fromfile=get(D/"file-times.json.gz");groups=defaultdict(list);blocks=defaultdict(list)
    for t,q,mode,rep,pos,arm,ns in timings:
        groups[mode,arm,q].append(ns/1e6);blocks[mode,q,rep].append((pos,arm))
    for t,q,rep,pos,arm,ns in fromfile:
        groups["file",arm,q].append(ns/1e6);blocks["file",q,rep].append((pos,arm))
    assert len(timings)==3840 and len(fromfile)==288
    assert all(len({a for i,a in v})==len({i for i,a in v})==4 for v in blocks.values())
    for key in ("warm","embeddings","file"):
        tab=ft["per_query_ms"] if key=="file" else summary["summary"][key]["question_medians_ms"]
        for arm,v in tab.items():
            meds=[statistics.median(ns) for (md,m,q),ns in groups.items() if md==key and m==arm]
            assert close(statistics.median(meds),v["p50"]) and close(statistics.mean(meds),v["mean"])
    for method in ("dense","cost","full_rgcn","wo_chunk_adjacency"):
        for i in (1,2):
            x=get(D/f"memory-{method}-{i}.json")
            assert x["sha"]=={q:replay[q]["arms"][method]["order_sha"] for q,t in plan["panel"][:8]}
    print(f"{len(h)} files; 3840 warm/embedding and 288 file-path timings, 384 native endpoint checks and 8 isolated memory processes verified")
if __name__=="__main__":main()
