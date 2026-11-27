"""Export charged measured records and the production codec for every workshop subset."""
import gzip
import json
from hashlib import sha256
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
R60=HERE.parent
sys.path.insert(0,str(R60/"coverage"))
from coverage import full,pack_exceptions,EXCEPTION
from lazy_reader import entry_size,POST,varints
from summary_cache import encode,XOR

IDS=[13,45,88,131,173,207,239,281]
EVENTS=[[0,1,2],[0,1,3],[0,2,3],[0,1,4],[0,1,2,4],[0,2,4],[0,1,3],[0,3,4]]
NAMES=["reader.py","test_reader.py","store.py","test_cache.py","schema.py"]


def load(p):
    blob=p.read_bytes()
    return json.loads(gzip.decompress(blob) if p.suffix==".gz" else blob)


def registry():
    src=load(R60/"coverage/results.json")
    obs=load(R60/"observed/results.json")["spans"]
    perf=load(R60/"hot_delta/results.json")
    data={}
    for label in ("old12/B","r59/B","new/B","old12/long","r59/long","new/long"):
        g=src[label]
        out={}
        for cap in (1024,4096):
            sysdata={}
            for m in ("exact","xor","lazy","notify"):
                row=g["arms"][f"{cap}/{m}"]
                sysdata[m]={k:row.get(k,0) for k in ("charged","posting_bytes","body_bytes","sql_calls","queries","certified_multiple","guard_fallback","exception_insertions")}
            projects={k.split("/",2)[-1]:{m:v[f"{cap}/{m}"] for m in ("exact","xor","lazy","notify")} for k,v in g["charges"].items()}
            out[str(cap)]=dict(all=sysdata,projects=projects)
        data[label]=out
    packets={}
    def spell(p):
        return dict(hex=p.hex(" "),payload=len(p),entry=entry_size((POST,0),p))
    for mask in range(1<<len(IDS)):
        exc=[j for i,j in enumerate(IDS) if mask & (1<<i)]
        packets[str(mask)]=spell(pack_exceptions(len(IDS),exc))
    return dict(cases=data,ids=IDS,events=EVENTS,names=NAMES,packets=packets,
                exact=spell(full(IDS)),xor=spell(encode(IDS,XOR)),body=[len(varints(v)) for v in EVENTS],
                observed={m:{a:obs[m]["arms"]["1024/"+a]["charged"] for a in ("exact","xor","joint","events")} for m in ("16","4")},
                coverage_obs={k:{a:w["charged"] for a,w in v["methods"].items()} for k,v in load(R60/"observed_coverage/results.json").items()},cpu=perf)


if __name__=="__main__":
    data=registry()
    html=(HERE/"template.html").read_text("utf8").replace("@@DATA@@",json.dumps(data,separators=(",",":")).replace("<","\\u003c"))
    (HERE/"index.html").write_bytes(html.encode())
    print(len(html.encode()),sha256(html.encode()).hexdigest())
