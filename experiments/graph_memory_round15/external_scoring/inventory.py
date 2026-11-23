"""Inspect only identifiers and available revision metadata; external truth values are not projected."""
import collections,gzip,hashlib,json,re,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]
CACHE=Path("D:/CodexResearch/x20-round15-external-scoring")
I="bd546b8ec1067eb4690cc0677a05320e88e35ff4"
E="bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9"
def get(uri,name):
    path=CACHE/name
    if not path.exists():
        with urllib.request.urlopen(urllib.request.Request(uri,headers={"User-Agent":"agent-memory-research"}),timeout=90) as res:b=res.read()
        path.write_bytes(b)
    return path.read_bytes()
def normalized(s):
    return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    sources=[BASE/"graph_memory_round13/reformulation/inputs.json.gz",BASE/"graph_memory_round13/reformulation/replication/inputs.json.gz",BASE/"graph_memory_round14/grounded/cases.gz"]
    local={normalized(r["iid"]):r["iid"] for f in sources for r in load(f)}
    named={}
    for split in ["test","transformed_swe_bench"]:
        uri=f"https://raw.githubusercontent.com/mohammad-nour-alawad/IssueLoc-bench/{I}/issueloc_bench_manifest/tasks/{split}.jsonl"
        named["IssueLoc-"+split]=(uri,"issueloc-"+split+".jsonl")
    named["SWE-Explore"]=(f"https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench/resolve/{E}/bench.final.public.jsonl","swe-explore.jsonl")
    out={}
    for tag,(uri,name) in named.items():
        raw=get(uri,name);rows=[json.loads(l) for l in raw.splitlines() if l.strip()]
        cols=[k for k in rows[0] if k in ("instance_id","task_id","repo","repo_name","base_commit","commit","base_sha","repo_dir","instance","id","snapshot_commit","pr_number")]
        select=[{k:r.get(k) for k in cols} for r in rows]
        intersect=[]
        for r in select:
            if r.get("repo") and r.get("pr_number"):
                key=normalized(r["repo"].replace("/","__")+"-"+str(r["pr_number"]))
                if key in local:
                    intersect.append(dict(native=r,local=local[key],rule="exact repository and PR"));continue
            for k in ("instance_id","task_id","instance","id"):
                v=r.get(k)
                if v and normalized(str(v)) in local:
                    intersect.append(dict(native=r,local=local[normalized(str(v))]));break
        out[tag]=dict(source=uri,bytes=len(raw),sha=hashlib.sha256(raw).hexdigest(),n=len(rows),safe_fields=cols,intersect=intersect,structure=list(rows[0]))
        print(tag,len(rows),cols,len(intersect),select[0])
    dest={"unique_preexisting_tasks":len(local),"panels":out}
    (ROOT/"coverage.json").write_text(json.dumps(dest,indent=1)+"\n",encoding="utf8")
if __name__=="__main__":main()
