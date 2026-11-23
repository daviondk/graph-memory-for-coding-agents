"""Public anonymous artifact index. Does not request or execute trajectory text."""
import concurrent.futures
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
REV="df29287116fa1565b3fd6b485022cd6090dc0b27"
HF="3130aeeaeb2b8d292c29f4c8e23303be7463732c"
TRAJ="e40e04d41c04e4eb4bae181ebdd41b61c688081b"
GH="https://api.github.com/repos/xiaoqi-7/GraphMemory"
REGEX=r"prepared\.jsonl|judg.*\.jsonl|predictions?\.|\.ckpt$|\.safetensors$|\.bin$|/per_task|per.task.*json|\.pt$"

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"agent-memory-public-artifact-audit/1.0","Accept":"*/*"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            b=r.read(25000000)
            return r.status,b
    except urllib.error.HTTPError as e:
        return e.code,b""
    except Exception as e:
        return 0,type(e).__name__.encode()

URL={
 "refs":GH+"/branches?per_page=100","releases":GH+"/releases?per_page=100","tags":GH+"/tags?per_page=100",
 "public_tree":GH+"/git/trees/"+REV+"?recursive=1","commits":GH+"/commits?per_page=100",
 "direct_e10":GH+"/contents/results/isetrace/e10-end-to-end-qa/prepared.jsonl?ref="+REV,
 "hf_queries":"https://huggingface.co/api/datasets/HazeLocus/ISETrace-Memory-Queries/tree/"+HF+"?recursive=true&expand=true&limit=100",
 "hf_raw":"https://huggingface.co/api/datasets/valiere/ISETrace/tree/"+TRAJ+"?recursive=true&expand=true&limit=100",
 "hf_repositories_datasets":"https://huggingface.co/api/datasets?search=ISETrace&limit=100",
 "hf_repositories_models":"https://huggingface.co/api/models?search=ISETrace&limit=100",
 "hf_author_datasets":"https://huggingface.co/api/datasets?author=HazeLocus&limit=100",
 "hf_author_models":"https://huggingface.co/api/models?author=HazeLocus&limit=100",
 "zenodo":"https://zenodo.org/api/records?q="+urllib.parse.quote('"ISETrace"')+"&size=50",
 "osf":"https://api.osf.io/v2/nodes/?filter%5Btitle%5D=ISETrace&page%5Bsize%5D=100",
 "datacite":"https://api.datacite.org/dois?query=ISETrace&page%5Bsize%5D=50",
 "arxiv_source":"https://arxiv.org/src/2609.25913v3",
 "vibe_data":"https://huggingface.co/api/datasets/Tongyi-ConvAI/VibeMemBench",
 "independent":"https://api.github.com/repos/GiulioDER/agent-memory-bench/git/trees/c1b15726f1153b02dda0490ca1936bb86a809514?recursive=1",
}
def process(it):
    k,url=it
    status,b=fetch(url)
    r=dict(url=url,status=status,bytes=len(b),body_sha256=hashlib.sha256(b).hexdigest())
    if status!=200:
        return k,r
    if k=="arxiv_source":
        try:
            with tarfile.open(fileobj=io.BytesIO(b),mode="r:*") as tar:
                r["files"]=[(m.name,m.size) for m in tar.getmembers() if m.isfile()]
                r["output_sources"]=[n for n,_ in r["files"] if re.search(REGEX,n,re.I) or re.search(r"\.(csv|jsonl|json|parquet|gz|zip)$",n)]
        except tarfile.ReadError:
            r["content"]="non-tar response"
        return k,r
    try:
        d=json.loads(b)
    except ValueError:
        r["content"]="non-JSON response"
        return k,r
    if k=="public_tree":
        files=[v for v in d["tree"] if v["type"]=="blob"]
        r.update(n_files=len(files),total_blob_bytes=sum(x.get("size",0) for x in files),truncated=d["truncated"],
                 result_dirs=[x["path"] for x in files if x["path"].startswith(("runs/","results/","data/processed/"))],
                 result_patterns=[x["path"] for x in files if re.search(REGEX,x["path"],re.I)])
    elif k=="independent":
        r.update(n=len(d["tree"]),truncated=d["truncated"],task_top=sorted(set(x["path"].split("/")[1] for x in d["tree"] if x["path"].startswith("tasks/"))))
    elif k in ("hf_queries","hf_raw"):
        r["data_files"]=[(f["path"],f["size"]) for f in d if f.get("type")=="file"]
    elif k.startswith("hf_"):
        r["identifiers"]=[x.get("id",x.get("modelId")) for x in d]
    elif k=="datacite":
        r["total"]=d["meta"]["total"]
        r["ids"]=[x["id"] for x in d["data"]]
    elif k=="zenodo":
        r["total"]=d["hits"]["total"]
        r["ids"]=[x["id"] for x in d["hits"]["hits"]]
    elif k=="osf":
        r["ids"]=[x["id"] for x in d["data"]]
        r["next"]=d["links"].get("next")
    elif k=="vibe_data":
        r.update(sha=d.get("sha"),n_files=len(d.get("siblings",[])))
    elif isinstance(d,list):
        r["count"]=len(d)
        r["ids"]=[x.get("name",x.get("sha",x.get("tag_name"))) for x in d]
        if k=="releases":
            r["assets"]=[a["browser_download_url"] for x in d for a in x["assets"]]
    return k,r

def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        got=dict(ex.map(process,URL.items()))
    bare=Path(os.environ.get("GRAPHMEMORY_BARE","D:/CodexResearch/x20-published-output-audit/graph.git"))
    git=lambda *args:subprocess.check_output(["git","-C",str(bare),*args],text=True).strip()
    tree=git("ls-tree","-r","-l","HEAD").splitlines()
    objs=[x.split("\t",1)[1] for x in tree]
    assert git("rev-parse","HEAD")==REV and git("rev-parse","--is-shallow-repository")=="false"
    got["full_git"]=dict(revision=REV,refs=git("show-ref").splitlines(),commits=int(git("rev-list","--count","--all")),
       n_files=len(objs),blob_bytes=sum(int(x.split("\t",1)[0].split()[-1]) for x in tree),
       output_prefix=[s for s in objs if s.startswith(("results/","runs/","data/processed/"))],
       possible_prediction_binaries=[s for s in objs if re.search(REGEX,s,re.I)])
    p=HERE/"surface-audit.json"
    assert not p.exists()
    p.write_text(json.dumps(got,ensure_ascii=False,indent=2)+"\n",encoding="utf8",newline="\n")
    for k,r in got.items():
        print(k,r.get("status"),str({a:v for a,v in r.items() if a in ("count","total","n_files","n","ids","identifiers","task_top","output_sources","sha","commits")})[:360])
if __name__=="__main__":
    main()
