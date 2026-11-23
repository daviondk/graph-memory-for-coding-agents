"""Supplement direct registry search, true flat BM25 match and source-query schema; zero author prediction rows."""
import gzip
import hashlib
import json
import urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"agent-memory-public-artifact-audit/1.0"}),timeout=25) as r:
        b=r.read()
        return dict(url=url,status=r.status,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()),json.loads(b)
def main():
    z,records=get("https://zenodo.org/api/records?q=ISETrace")
    z["hits"]=records["hits"]["total"]
    z["record_ids"]=[x["id"] for x in records["hits"]["hits"]]
    m,d=get("https://huggingface.co/api/models/valiere/ISETrace-SFT-8B")
    m.update(pipeline=d.get("pipeline_tag"),architectures=d.get("config",{}).get("architectures"),revision=d.get("sha"),
             files=[x["rfilename"] for x in d["siblings"]])
    lme,d=get("https://api.github.com/repos/xiaowu0162/LongMemEval-V2/commits/main")
    lme["revision"]=d["sha"]
    x=json.loads(gzip.decompress((HERE.parent.parent/"graph_memory_round18/isetrace_official/outcomes.json.gz").read_bytes()))
    flat=[r for r in x if r["view"]=="flat" and r["arm"]=="prefix"]
    assert len(flat)==2000
    a={"n":len(flat),"hits":sum(int(r["full_support"]) for r in flat),"cov":sum(r["coverage"] for r in flat)/len(flat)}
    a["rounded_matches"]=a["hits"]==759 and round(100*a["cov"],2)==45.62
    assert a["rounded_matches"]
    final=dict(zenodo_unquoted=z,unrelated_SFT_model=m,LongMemEval2=lme,v3_BM25_native=a)
    (HERE/"supplemental-audit.json").write_text(json.dumps(final,indent=2)+"\n",encoding="utf8",newline="\n")
    print(z["hits"],m["pipeline"],lme["revision"],a)
if __name__=="__main__":
    main()
