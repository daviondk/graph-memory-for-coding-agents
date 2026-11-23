"""Offline integrity and outcome audit, using only the standard library and the archived coordinates."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean

D=Path(__file__).resolve().parent
def data(name):
    p=D/name;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def hashed(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def union(spans):
    parts=collections.defaultdict(list)
    for s in spans:parts[s["event_id"],s["json_pointer"]].append((s["char_start"],s["char_end"]))
    result={}
    for key, intervals in parts.items():
        out=[]
        for start,end in sorted(intervals):
            if out and start<=out[-1][1]:out[-1]=(out[-1][0],max(out[-1][1],end))
            else:out.append((start,end))
        result[key]=out
    return result
def evaluate(gold,spans):
    memory=union(spans);gt=union(gold)
    size=sum(b-a for terms in gt.values() for a,b in terms)
    hit=sum(max(0,min(b,d)-max(a,c)) for key,terms in gt.items() for a,b in terms for c,d in memory.get(key,[]))
    cost=sum(s["char_end"]-s["char_start"] for s in spans)
    return float(hit==size),hit/size,hit/cost if cost else 0
def main():
    seal=data("forecast-lock.json")
    assert seal["plan"]==hashed(D/"ranking-plan.json")
    truth=data("gold-spans.json.gz");outcomes=data("outcomes.json.gz")
    obs={(r["q"],r["view"],r["arm"]):r for r in outcomes}
    assert len(obs)==len(outcomes)
    tasks=set();n=0
    for path,h in seal["forecasts"].items():
        assert hashed(D/path)==h
        with gzip.open(D/path,"rb") as stream:
            for line in stream:
                item=json.loads(line)
                for q,views in item["queries"].items():
                    assert q not in tasks
                    tasks.add(q)
                    for v,rec in views.items():
                        ranked=rec["ranked"];lookup={r["node_id"]:r for r in ranked}
                        if rec["partial"] is not None:lookup[rec["partial"]["node_id"]]=rec["partial"]
                        p=rec["arms"]["prefix"];assert p==[node["node_id"] for node in ranked[:len(p)]]
                        if len(p)<len(ranked):assert sum(x["token_count"] for x in ranked[:len(p)+1])>2048
                        for pol,ids in rec["arms"].items():
                            assert ids[:len(p)]==p and len(ids)==len(set(ids))
                            nodes=[lookup[k] for k in ids]
                            fields=[s for node in nodes for s in node["source_spans"]]
                            result=obs[q,v,pol];assert result["tokens"]==sum(a["token_count"] for a in nodes)<=2048
                            stats=evaluate(truth[q],fields)
                            for k,val in zip(("full_support","coverage","density"),stats,strict=True):assert abs(result[k]-val)<1e-12
                            n+=1
    assert n==len(outcomes) and tasks==set(truth)
    summary=data("results.json")
    assert sum(r["full_support"] for r in outcomes if r['view']=="flat" and r["arm"]=="prefix")==summary["official_calibration"]["observed_count"]
    for key,ms in summary["all"]["metrics"].items():
        v,h=key.split("/");sel=[r for r in outcomes if r["view"]==v and r["arm"]==h]
        for k in ("full_support","coverage","density","tokens"):assert abs(ms[k]-mean(r[k] for r in sel))<1e-12
    manifest=D/"MANIFEST_SHA256.json"
    if manifest.exists():
        for path,h in data(manifest.name).items():assert hashed(D/path)==h
    print("verified",n,"task/arms",len(tasks),"queries and",len(seal["forecasts"]),"ranking shards")
if __name__=="__main__":main()
