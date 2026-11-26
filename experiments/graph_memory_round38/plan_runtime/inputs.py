"""Only prior view/action metadata and the current edit reach runtime inputs."""
from pathlib import Path
from hashlib import sha256
from collections import defaultdict
import json,gzip
D=Path(__file__).resolve().parent
W=D.parents[1]/"graph_memory_round37";V=W/"code_visibility";S=W/"code_store";P=W/"edit_demand";H=W/"plan_choice"
def sha(f):return sha256(f.read_bytes()).hexdigest()
def h(s):return sha256(s.encode()).hexdigest()
def get(f):return json.loads(gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes())
def put(f,x):
    raw=(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode()
    f.write_bytes(gzip.compress(raw,mtime=0) if f.suffix==".gz" else raw)
    return sha(f)
def prepare():
    assert sha(H/"manifest.json")=="0ae77f5c7884b6f393d02027dd50323fdac2c5c3b6fc0511533ea53960d302cc"
    raw=get(P/"prefixes.json.gz");follow={r["q"]:r for r in get(P/"followup.json.gz")}
    panel=get(P/"physical-plan.json")["panel"];ev=get(V/"events.json.gz");hist=get(H/"history.json.gz")
    s={};future={}
    for q in panel:
        r=follow[q];x=raw[q];path=x["path"]
        past="".join("v" if e[1]=="read" else "e" for e in ev[r["rid"]]["events"] if e[0]<=r["prev"] and e[1] in ("read","edit") and e[2]==path)
        assert [r["edit"]-r["prev"],past.count("v"),past.count("e")]==hist[q]
        s[q]={**x,"past_types":past,"prev":r["prev"],"current":r["edit"],"repo":r["repo"]}
        future[q]=dict(reads=r["strict"]["reads"],issue=r["issue"],repo=r["repo"])
    put(D/"plan.json",dict(panel=panel,inputs=put(D/"prefixes.json.gz",s),schedule=put(D/"schedule.json.gz",future),
       code=sha(Path(__file__)),engine=sha(D/"engine.py"),timing=sha(D/"run.py"),protocol=sha(D/"PROTOCOL_RU.md"),
       frozen_models=sha(H/"models.json"),frozen_choices=sha(H/"decisions.json.gz"),parent=sha(H/"manifest.json")))
if __name__=="__main__":prepare()
