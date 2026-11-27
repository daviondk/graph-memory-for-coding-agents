"""Generate a self-contained ICDE demonstration from saved measurements. Runtime uses no network."""
from collections import defaultdict
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
EXP=HERE.parent
RESTART=EXP/"restart";CACHE=EXP/"task_cache"
METHODS=["cold","recent1024","largest1024","demand1024","recent4096","largest4096","demand4096","full"]

def load(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)

def onerep(rows):
    queries=[q for row in rows for q in row["queries"]]
    post=[q for q in queries if q[0]]
    def s(k):return sum(r["stats"][k] for r in rows)
    def t(k):return sum(r["times"][k] for r in rows)
    times=[t(k) for k in ("source_writes_ns","demand_ns","select_ns","persist_ns","checkpoint_ns","open_ns")]
    return dict(write=s("snapshot_write"),load=s("snapshot_load"),receipt=s("receipt_bytes"),
                posting=sum(q[4] for q in post),body=sum(q[6] for q in post),useful=s("snapshot_useful"),seen=s("snapshot_events"),
                n=len(post),all_n=len(queries),pre_s=sum(q[1] for q in queries if not q[0]),post_s=sum(q[1] for q in post),
                store_s=times[3],open_s=times[5],select_s=times[2],total_s=sum(times)+sum(q[1] for q in queries),
                sql=sum(q[2]+q[3] for q in post),db=s("database_bytes"),wal=s("wal_bytes"))

def merge(rows):
    blocks=[onerep([r for r in rows if r["rep"]==rep]) for rep in (0,1,2)]
    return {k:int(median(v[k] for v in blocks)) if k.endswith("_s") else invariant(v[k] for v in blocks) for k in blocks[0]}

def invariant(xs):
    data=set(xs);assert len(data)==1
    return data.pop()

def traffic(r):return sum(r[k] for k in ("write","load","receipt","posting","body"))

def data():
    measured=load(RESTART/"runs.json.gz");runs=measured["runs"]
    official=load(RESTART/"results.json");assert len(runs)==216
    restart={}
    for panel in ("B","long"):
        selected=[r for r in runs if r["panel"]==panel]
        repos=sorted({r["project"] for r in selected})
        restart[panel]={}
        for repo in ["All projects"]+repos:
            rs=[r for r in selected if repo=="All projects" or r["project"]==repo]
            restart[panel][repo]={}
            for m in METHODS:
                obj=merge([r for r in rs if r["method"]==m])
                restart[panel][repo][m]=obj
                if repo=="All projects":
                    ref=official[panel+"-"+m]
                    assert traffic(obj)==ref["charged_bytes"] and obj["post_s"]==ref["post_read_ns"][0] and obj["total_s"]==ref["end_to_end_ns"][0]
                    assert obj["store_s"]==ref["persist_ns"][0] and obj["n"]==ref["post_n"]
    windows=load(CACHE/"windows.json.gz")
    fixed=load(CACHE/"results.json")["all"]
    compact=load(CACHE/"compact-results.json")
    caches={}
    for cap in (4096,16384,65536):
        arms={}
        for m in ("global","global_intern","file","file_intern","segmented","segmented_intern"):
            v=fixed["arms"][f"{cap}_12_{m}"]
            arms[m]=[v["hit_bytes"],v["full"]]
        for m in ("none","file","all"):
            v=compact[f"{cap}_{m}"]
            arms["packed_"+m]=[v["hit_bytes"],v["full"]]
        caches[str(cap)]=arms
    projects=sorted({r["repo"] for r in windows})
    # Export only aggregate counts and non-identifying window ordinals. No paths, issue IDs or source text.
    compact_windows=[]
    for r in windows:
        a=r["score"]["16384_12_file"];b=r["score"]["16384_12_file_intern"]
        actor=0 if "gpt4" in r["actor"] else 1
        assert actor==0 or "claude3.5" in r["actor"]
        compact_windows.append([projects.index(r["repo"]),actor,r["bytes"],a[0],b[0],a[1],b[1]])
    assert sum(r[3] for r in compact_windows)==caches["16384"]["file"][0] and len(compact_windows)==822
    sources=[RESTART/"runs.json.gz",RESTART/"results.json",CACHE/"windows.json.gz",CACHE/"results.json",CACHE/"compact-results.json"]
    return dict(restart=restart,methods=METHODS,cache=caches,projects=projects,windows=compact_windows,
                source={str(p.relative_to(EXP)).replace("\\","/"):sha256(p.read_bytes()).hexdigest() for p in sources})

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    payload=json.dumps(data(),ensure_ascii=True,separators=(",",":")).replace("<","\\u003c")
    tpl=(HERE/"template.html").read_text(encoding="utf-8")
    assert tpl.count("%%DATA%%")==1
    out=tpl.replace("%%DATA%%",payload).replace("\r\n","\n").encode()
    dest=HERE/"index.html"
    if args.verify:assert dest.read_bytes()==out
    else:dest.write_bytes(out)
    print(len(out),"bytes, sha256",sha256(out).hexdigest())
if __name__=="__main__":main()
