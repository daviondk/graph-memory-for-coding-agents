"""Freeze rankings using exactly three previously observed native editor reads per instance."""
import collections
import gzip
import hashlib
import io
import json
import keyword
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HOME=ROOT.parents[1]
STREAM=HOME/"graph_memory_round11/readback/views.gz"
STOP=set(keyword.kwlist)|set("self cls None True False str int list dict exception assert test return import from args kwargs".split())
def sha(b):return hashlib.sha256(b).hexdigest()
def load(f):
    b=f.read_bytes();return json.loads(gzip.decompress(b) if f.suffix==".gz" else b)
def save(name,x):
    b=json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    (ROOT/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def rank_views(events):
    data={};order=[]
    for index,r in enumerate(events):
        p=r['path'];entry=data.setdefault(p,dict(first=index,last=index,count=0,lines={},ids=set()))
        entry["last"]=index;entry["count"]+=1
        for line,text in r['lines']:
            entry["lines"][line]=text
            entry["ids"].update(s for s in re.findall("[a-zA-Z_][a-zA-Z0-9_]*",text) if len(s)>=5 and s not in STOP)
    weights={p:sum(len(obj["ids"] & o["ids"])/max(1,len(obj["ids"]|o["ids"])) for q,o in data.items() if q!=p) for p,obj in data.items()}
    sorters={"recent":lambda p:-data[p]["last"],"first":lambda p:data[p]["first"],
             "repeated":lambda p:(-data[p]["count"],-data[p]["last"]),
             "graph":lambda p:(-data[p]["count"],-weights[p],-data[p]["last"])}
    result={}
    for arm,key in sorters.items():
        files=sorted(data,key=lambda p:(key(p),p))[:3]
        budget=60;regions=[]
        for f in files:
            selected=sorted(data[f]["lines"])[:budget]
            for line in selected:
                if regions and regions[-1][0]==f and regions[-1][2]+1==line:regions[-1][2]=line
                else:regions.append([f,line,line])
            budget-=len(selected)
        result[arm]=dict(files=files,regions=regions,lines=60-budget)
    return result
def main():
    source=load(STREAM)
    forecasts={k:{"panel":v["panel"],"repo":v["repo"],"number_of_views":len(v["views"][:3]),
                  "arms":rank_views(v["views"][:3])} for k,v in source.items()}
    save("published-forecast.gz",forecasts)
    save("views-seal.json",{"archive_sha":sha(STREAM.read_bytes()),"files":{n:sha((ROOT/n).read_bytes()) for n in
         ("views.py","ARCHIVED_VIEWS_RU.md","published-forecast.gz")},"n":len(source),
         "with_evidence":sum(bool(r["number_of_views"]) for r in forecasts.values())})
    print(load(ROOT/"views-seal.json"))
if __name__=="__main__":main()
