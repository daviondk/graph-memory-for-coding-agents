"""Independently check all typed choices, menu accessibility, and actual opened source spans."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
D=Path(__file__).resolve().parent
def read(name):
    p=D/name;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ranges(spans):
    tmp=defaultdict(list)
    for v in spans:tmp[v["event_id"],v["json_pointer"]].append((v["char_start"],v["char_end"]))
    out={}
    for k,l in tmp.items():
        halves=[]
        for a,b in sorted(l):
            if halves and a<=halves[-1][1]:halves[-1]=(halves[-1][0],max(halves[-1][1],b))
            else:halves.append((a,b))
        out[k]=halves
    return out
def calc(g,rows):
    original=[s for r in rows for s in r["source_spans"]];look=ranges(original)
    gc=sum(b-a for l in g.values() for a,b in l);returned=sum(s["char_end"]-s["char_start"] for s in original)
    hit=sum(max(0,min(b,y)-max(a,x)) for k,l in g.items() for a,b in l for x,y in look.get(k,[]))
    return {"full":int(hit==gc),"coverage":hit/gc,"density":hit/returned if returned else 0}
def main():
    for f,h in read("MANIFEST_SHA256.json").items():assert sha(D/f)==h
    roster=read("panel.json.gz");g={q:ranges(v) for q,v in read("gold-panel.json.gz").items()};results=read("outcomes.json.gz")
    log={x["prompt_sha256"]:x for x in (json.loads(l) for l in (D/"open-receipts.jsonl").read_bytes().splitlines())}
    assert sha(D/"open-receipts.jsonl")==read("response-lock.json")["responses"]
    assert len(roster)==len({r["t"] for r in roster.values()})==36
    assert {c["key"] for m in roster.values() for c in m["arms"].values() if c["key"]}==set(log)
    for q,rec in roster.items():
        for arm,v in rec["arms"].items():
            chosen=log.get(v["key"],{"valid":False,"selected":None})
            blocks={s["ix"]:s for s in v["retrieved"]};events={int(e):[blocks[j] for j in info["indices"]] for e,info in v["groups"].items()}
            assert all(all(row["e"]==eid for row in ss) for eid,ss in events.items())
            assert sum(z["token_count"] for z in v["retrieved"])==v["raw_tokens"]<=2048
            assert sum(z["token_count"] for ss in events.values() for z in ss)==v["visible_tokens"]<=v["raw_tokens"] and v["stored"]<=8192
            if chosen["valid"]:
                assert chosen["selected"] in events and chosen["opened_sha256"]==v["groups"][str(chosen["selected"])]["shown_digest"]
                actual=events[chosen["selected"]]
            else:actual=[]
            methods={"qwen":calc(g[q],actual),"top1":calc(g[q],events.get(v["bm25_event"],[])),
                     "oracle":max([calc(g[q],s) for s in events.values()] or [calc(g[q],[])],key=lambda x:(x["full"],x["coverage"],x["density"])),
                     "all_visible":calc(g[q],[b for ss in events.values() for b in ss]),"raw_read":calc(g[q],v["retrieved"])}
            for m,stats in methods.items():
                for k,x in stats.items():assert abs(results[q]["arms"][arm][m][k]-x)<1e-12
    sums=read("results.json")
    for sec,subset in (("all",list(results.values())),("new_equal",[x for x in results.values() if x["same_prompt"]]),("new_different",[x for x in results.values() if not x["same_prompt"]])):
        s=sums[sec];assert s["n"]==len(subset)
        for arm,m in s.get("stats",{}).items():
            for method in ("qwen","top1","oracle","all_visible","raw_read"):
                assert sum(x["arms"][arm][method]["full"] for x in subset)==m[method]["full"]
                assert abs(mean(x["arms"][arm][method]["coverage"] for x in subset)-m[method]["coverage"])<1e-12
    print("verified",len(log),"actual model decisions and",2*len(roster),"paired conditions across",len(g),"trajectories")
if __name__=="__main__":main()
