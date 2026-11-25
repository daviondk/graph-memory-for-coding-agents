"""Verify curated primary records and log transparent query endpoints; text or code returned is not executed."""
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
import re,json
from formats import D,write
class Meta(HTMLParser):
    def __init__(self):super().__init__();self.meta={}
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=="meta" and "name" in d and "content" in d:self.meta.setdefault(d["name"],[]).append(d["content"])
def fetch(url):
    req=Request(url,headers={"User-Agent":"AgentMemoryResearch/1.0 academic bibliographic metadata"})
    with urlopen(req,timeout=25) as r:return r.read()
records=[
 ("STALE","2605.06527","https://github.com/icedreamc/STALE","https://huggingface.co/datasets/STALEproj/STALE"),
 ("rollback","2608.10502","https://github.com/xiaoqi-7/memory-rollback",""),
 ("obsolete","2610.36308","https://github.com/oleeviyababu/Memory_Conflict",""),
 ("HaluMem","2511.03506","https://github.com/MemTensor/HaluMem","https://aclanthology.org/2026.emnlp-main.220/"),
 ("LongMemEval","2410.10813","https://github.com/xiaowu0162/LongMemEval","https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned"),
 ("MemoryAgentBench","2507.05257","https://github.com/HUST-AI-HYZ/MemoryAgentBench","https://huggingface.co/datasets/ai-hyz/MemoryAgentBench"),
 ("Zep","2501.13956","https://github.com/getzep/graphiti",""),
 ("Folio","2611.16627","",""),
 ("RLM","2512.24601","",""),
 ("ISETrace","2609.25913","",""),
 ("MemDelta","2606.29914","",""),
 ("LongMemEvalV2","2605.12493","https://github.com/xiaowu0162/LongMemEval-V2",""),
 ("handoff","2611.22245","",""),
 ("ReadAgent","2402.09727","","https://proceedings.mlr.press/v235/lee24c.html")]
def verify(rec):
    name,id,code,source=rec;u="https://arxiv.org/abs/"+id
    parser=Meta();parser.feed(fetch(u).decode())
    bib=parser.meta;title=bib["citation_title"][0];authors=bib.get("citation_author",[])
    doi="10.48550/arXiv."+id
    try:
        dc=json.loads(fetch("https://api.datacite.org/dois/"+doi))["data"]["attributes"]
        dctitles=[t["title"] for t in dc["titles"]]
        status="registered"
    except Exception as e:dctitles=[];status=type(e).__name__
    return dict(key=name,arxiv=id,url=u,title=title,authors=authors,date=bib.get("citation_date",[]),doi=doi,datacite_status=status,datacite_titles=dctitles,code=code,additional_primary=source)
DISCOVERY=["agent memory obsolete stale facts benchmark conflict resolution","LLM memory retraction superseded claims persistent source provenance","recoverable context folding page handles agent memory","long context agent gist retrieval bounded pages"]
def discover(service,query):
    if service=="OpenAlex": url="https://api.openalex.org/works?"+urlencode(dict(search=query,per_page=5))
    else:url="https://api.crossref.org/works?"+urlencode({"query.bibliographic":query,"rows":5})
    try:
        x=json.loads(fetch(url))
        if service=="OpenAlex":data=[{"title":z["title"],"id":z.get("doi") or z["id"]} for z in x["results"]]
        else:data=[{"title":(z.get("title") or [""])[0],"id":z.get("DOI")} for z in x["message"]["items"]]
        return dict(service=service,query=query,url=url,records=data)
    except Exception as ex:return dict(service=service,query=query,url=url,error=str(ex))
if __name__=="__main__":
    with ThreadPoolExecutor(4) as pool:
        evidence=list(pool.map(verify,records))
    write(D/"primary-sources.json",evidence)
    with ThreadPoolExecutor(3) as pool:
        out=list(pool.map(lambda x:discover(*x),[(s,q) for s in ("OpenAlex","Crossref") for q in DISCOVERY]))
    write(D/"discovery.json",out)
    print([(x["key"],x["title"],x["datacite_status"]) for x in evidence])

