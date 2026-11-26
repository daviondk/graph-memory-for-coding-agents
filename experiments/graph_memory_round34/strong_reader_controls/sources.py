"""Record primary discovery results, repository inventory and numerical tables from the paper."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib, json, re
import requests
from bs4 import BeautifulSoup

HERE=Path(__file__).resolve().parent
URLS={
 "paper":"https://arxiv.org/html/2609.25913v3","upstream_paper":"https://arxiv.org/html/2606.11520",
 "openalex_citing":"https://api.openalex.org/works?filter=cites:W7213512630&per_page=100",
 "openalex_query":"https://api.openalex.org/works?search=%22ISETrace%22&per_page=100",
 "s2":"https://api.semanticscholar.org/graph/v1/paper/ARXIV:2609.25913/citations?fields=title,externalIds",
 "hf_models":"https://huggingface.co/api/models?author=HazeLocus&limit=100",
 "hf_model_search":"https://huggingface.co/api/models?search=ISETrace&limit=100",
 "hf_datasets":"https://huggingface.co/api/datasets?author=HazeLocus&limit=100",
 "data":"https://huggingface.co/api/datasets/HazeLocus/ISETrace-Memory-Queries/tree/main?recursive=true",
 "repo_tree":"https://api.github.com/repos/xiaoqi-7/GraphMemory/git/trees/main?recursive=1",
 "release":"https://api.github.com/repos/xiaoqi-7/GraphMemory/releases",
 "branch":"https://api.github.com/repos/xiaoqi-7/GraphMemory/branches",
 "readme":"https://raw.githubusercontent.com/xiaoqi-7/GraphMemory/main/README.md",
 "memshift":"https://arxiv.org/html/2611.02338","schema":"https://arxiv.org/html/2610.19611"}
def fetch(arg):
    k,u=arg
    try:
        r=requests.get(u,timeout=18); out={"url":u,"status":r.status_code,"sha256":hashlib.sha256(r.content).hexdigest()}
        if r.status_code!=200:return k,out
        if k.startswith("openalex"):out["count"]=r.json()["meta"]["count"];out["items"]=[[v["id"],v["display_name"],v.get("doi")] for v in r.json()["results"]]
        elif k in ("hf_models","hf_model_search","hf_datasets"):out["ids"]=[v["id"] for v in r.json()]
        elif k=="data":out["files"]=[v["path"] for v in r.json()]
        elif k=="repo_tree":
            v=r.json();out.update({"tree":v["sha"],"truncated":v["truncated"],"num_entries":len(v["tree"]),"blobs":[f["path"] for f in v["tree"] if f["type"]=="blob"]})
        elif k=="release":out["assets"]=[(v["tag_name"],[t["name"] for t in v["assets"]]) for v in r.json()]
        elif k=="branch":out["branches"]={v["name"]:v["commit"]["sha"] for v in r.json()}
        elif k=="s2":out["results"]=r.json().get("data",[])
        elif k=="readme":out["linked_urls"]=sorted(set(re.findall(r'https://[^\s)<>]+',r.text)))
        else:
            doc=BeautifulSoup(r.content,"html.parser")
            for tag in doc("annotation"):tag.decompose()
            out["sections"]=[h.get_text(" ",strip=True) for h in doc.select("h2.ltx_title_section, h2.ltx_title_appendix")]
            if k=="paper":
                out["tables"]={}
                for tag in doc.select("figure.ltx_table"):
                    out["tables"][tag["id"]]=[[cell.get_text(" ",strip=True) for cell in row.select(":scope > td,:scope > th")] for row in tag.select("tr")]
            else:
                for term in ("ISETrace","Full Support","2609.25913","When Does Execution Provenance"):
                    out.setdefault("mention_counts",{})[term]=doc.get_text(" ",strip=True).lower().count(term.lower())
        return k,out
    except (requests.RequestException,ValueError,KeyError) as e:
        return k,{"url":u,"error":str(e)}
if __name__=="__main__":
    with ThreadPoolExecutor(max_workers=7) as pool: results=dict(pool.map(fetch,URLS.items()))
    (HERE/"discovery.json").write_text(json.dumps(results,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print({k:v.get("status",v.get("error")) for k,v in results.items()})
