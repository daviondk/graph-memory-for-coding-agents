"""Inventory missing embeddings for the 80 extra development questions without loading gold."""
import hashlib,sqlite3,json,gzip
from pathlib import Path
from collections import defaultdict
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19"
CACHE=Path("D:/CodexResearch/x20-isetrace-runtime/write-dev-private/projection")
DB=Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3")
PS=Path("D:/CodexResearch/x20-isetrace-fine-train")
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def key(s):return hashlib.sha256(s.encode()).digest()
def group():
    cohort=load(OLD/"write_transfer/cohort.json");old={r["t"] for r in cohort if r["publication_dev500"]};ids={r["q"] for r in cohort if not r["publication_dev500"]};assert len(ids)==80
    files=[];texts={};subset={}
    for f in CACHE.glob("*.json.gz"):
        r=load(f);qs={q:s for q,s in r["q"] if q in ids}
        if not qs:continue
        files.append(f);t=r["t"]
        for q,s in qs.items():texts[key("query: "+s)]="query: "+s;subset[q]=t in old
        for p in r["pool"]:
            s=p["source_spans"][0];txt="passage: "+r["fields"][s["event_id"]][s["char_start"]:s["char_end"]];texts[key(txt)]=txt
    return files,texts,subset
if __name__=="__main__":
    files,texts,grouping=group();db=sqlite3.connect(DB.as_uri()+"?mode=ro",uri=True);known={k for k, in db.execute("select k from vectors where prec='ft'")}
    missing=[v for k,v in texts.items() if k not in known]
    print("files",len(files),"queries",len(grouping),"source repeated",sum(grouping.values()),"all strings",len(texts),"missing",len(missing),"missing chars",sum(map(len,missing)))

