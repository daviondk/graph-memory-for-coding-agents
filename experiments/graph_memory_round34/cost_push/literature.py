"""Preserve a bounded bibliographic search and identify which primary texts were inspected."""
import concurrent.futures,json,urllib.parse,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
QUERIES=("Top Rank Optimization in Linear Time Li Jin Zhou","Offline Retrieval Evaluation Without Evaluation Metrics Diaz Ferraro","cost-sensitive learning to rank McBride Wang")
SOURCES=("crossref","openalex")
def search(job):
    provider,q=job
    if provider=="crossref":
        url="https://api.crossref.org/works?"+urllib.parse.urlencode({"query.bibliographic":q,"rows":5,"select":"title,DOI,URL"})
    else:
        url="https://api.openalex.org/works?"+urllib.parse.urlencode({"search":q,"per_page":5,"select":"display_name,doi,id"})
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"GraphMemoryBibliography/1.0"})
        with urllib.request.urlopen(req,timeout=12) as fd: raw=json.load(fd)
        if provider=="crossref":hits=[{"title":(x.get("title") or [""])[0],"url":x.get("URL"),"doi":x.get("DOI")} for x in raw["message"]["items"]]
        else:hits=[{"title":x["display_name"],"url":x["id"],"doi":x.get("doi")} for x in raw["results"]]
        return {"source":provider,"q":q,"url":url,"records":hits,"status":"ok"}
    except Exception as ex:return {"source":provider,"q":q,"url":url,"status":str(ex)}
if __name__=="__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(search,[(s,q) for s in SOURCES for q in QUERIES]))
    out={"scope":"Targeted source verification. Up to 5 search records per query and database, non-exhaustive. Full-text checks are recorded in PRIOR_ART_RU.md.","queries":records}
    (HERE/"bibliographic-search.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print([(r["source"],r["status"],len(r.get("records",[]))) for r in records])
