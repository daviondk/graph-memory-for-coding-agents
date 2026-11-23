"""Independent, standard-library replay. Cross multiply integer scores and parse raw event IDs."""
from collections import Counter
from functools import cmp_to_key
from pathlib import Path
import gzip
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parent
OFF=ROOT.parents[1]/"isetrace_official";DENSE=ROOT.parents[1]/"isetrace_e5"
def get(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def sha(path):
    with path.open("rb") as fp:return hashlib.file_digest(fp,"sha256").hexdigest()
def manifest():
    return {p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}
def main():
    if "--write-manifest" in sys.argv:
        (ROOT/"MANIFEST_SHA256.json").write_text(json.dumps(manifest(),indent=2,sort_keys=True),encoding="utf8")
    assert get(ROOT/"MANIFEST_SHA256.json")==manifest()
    fseal=get(ROOT/"forecast-seal.json")
    assert sha(ROOT/"plan-seal.json")==fseal["plan"] and sha(ROOT/"forecasts.json.gz")==fseal["forecasts"]
    for path,key in ((OFF/"forecast-lock.json","bm25_seal"),(DENSE/"forecast-seal.json","dense_seal")):
        assert sha(path)==fseal[key]
        assert all(sha(path.parent/n)==h for n,h in get(path)["forecasts"].items())
    forecasts={row["q"]:row for row in get(ROOT/"forecasts.json.gz")}
    summary=get(ROOT/"results.json");obs=get(ROOT/"outcomes.json.gz")
    cells=Counter()
    for row in obs:
        assert row["tokens"]<=2048
        cells[row["arm"]]+=int(row["full_support"])
    assert len(obs)==24000 and all(v["fs_count"]==cells[k] for k,v in summary["summaries"].items())
    checked=0
    for i in range(8):
        eps={r["q"]:r for r in get(DENSE/f"forecasts-main-{i}.json.gz")}
        with gzip.open(OFF/f"forecasts-shard-{i}.jsonl.gz","rb") as fp:
            for line in fp:
                part=json.loads(line)
                for q,views in part["queries"].items():
                    sparse=views["provenance"]["ranked"];dense=eps[q]["rr"]
                    ids=sorted(n["node_id"] for n in dense);index={k:j for j,k in enumerate(ids)}
                    db={n["node_id"]:j+1 for j,n in enumerate(dense)}
                    ratios={};cost={};event={}
                    for j,n in enumerate(sparse,1):
                        k=n["node_id"];a=j+60;b=db[k]+60
                        ratios[k]=(a+b,a*b);cost[k]=n["token_count"]
                        role,cid=n["source_spans"][0]["event_id"].split(":")[1:];event[k]=(cid,role)
                    def compare(x,y,value=False):
                        xn,xd=ratios[x];yn,yd=ratios[y]
                        left=xn*yd;right=yn*xd
                        if value:
                            left,right=left**2*cost[y],right**2*cost[x]
                        return -1 if left>right else 1 if left<right else (-1 if x<y else int(x>y))
                    order=sorted(ids,key=cmp_to_key(compare))
                    frozen=forecasts[q]
                    assert hashlib.sha256("\n".join(order).encode()).hexdigest()==frozen["rank_sha"]
                    p=0;start=0
                    while p<len(order) and start+cost[order[p]]<=2048:
                        start+=cost[order[p]];p+=1
                    head=order[:p];tail=order[p:]
                    paired={(cid,"call" if role=="output" else "output") for cid,role in map(event.__getitem__,head)}
                    adjacent=[k for k in tail if event[k] in paired];rest=[k for k in tail if event[k] not in paired]
                    variants={"prefix":[],"skip":tail,"related":adjacent+rest,
                        "value":sorted(tail,key=cmp_to_key(lambda a,b:compare(a,b,True)))}
                    for arm,seq in variants.items():
                        selected=list(head);budget=2048-start
                        for k in seq:
                            if cost[k]<=budget:selected.append(k);budget-=cost[k]
                        assert [index[k] for k in selected]==frozen["arms"][arm]
                        checked+=1
    assert checked==8000
    print("Verified",checked,"RRF selections via integer cross-products and event IDs; calculated counts for",len(obs),"outcomes")
if __name__=="__main__":main()
