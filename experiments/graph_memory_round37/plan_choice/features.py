"""Features are available at the write. Issue and repository labels never enter this interface."""
from math import log1p
from pathlib import Path
import json,gzip,hashlib
from collections import defaultdict,Counter
D=Path(__file__).resolve().parent;P=D.parent/"edit_demand";V=D.parent/"code_visibility";S=D.parent/"code_store"
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,x):
    raw=(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw);return sha(p)
NAMES=["old_lines","receipt_lines","same_address","move_candidates","intersect_edit","absolute_shift","anchored","view_age","past_views","past_replaces"]

def vector(old,receipt,start,end,delta,age,past_views,past_replaces):
    shift=0;overlap=0;mentioned=0
    for n in old:
        if n in receipt:mentioned+=1
        if start is not None:
            if start<=n<=end:overlap+=1
            elif n>end and delta:shift+=1
    return [log1p(len(old)),log1p(len(receipt)),log1p(mentioned),log1p(shift),log1p(overlap),log1p(abs(delta or 0)),
            float(start is not None),log1p(age),log1p(past_views),log1p(past_replaces)]

def prepare():
    assert sha(P/"manifest.json")=="d420f7ea5033c0695243869ac02eabfc593e788cf4924d0b093fdc0409182e84"
    old=get(P/"prefixes.json.gz"); fu=get(P/"followup.json.gz"); ev=get(V/"events.json.gz")
    # All features, including on censored rows, are built by advancing the stream once.
    byid=defaultdict(dict)
    for r in fu:byid[r["rid"]][r["edit"]]=(r["q"],r["prev"])
    hist={};feat={}
    for rid,wanted in byid.items():
        nv=Counter();ne=Counter();last={}
        for e in ev[rid]["events"]:
            if len(e)<3:continue
            i,kind,path=e[:3]
            if i in wanted:
                q,prev=wanted[i];x=old[q]
                assert kind=="edit" and x["path"]==path and last[path]==prev
                xy=[i-prev,nv[path],ne[path]]
                hist[q]=xy;feat[q]=vector([t[0] for t in x["base"]],dict(x["receipt"]),x["start"],x["end"],x["delta"],*xy)
            if kind=="read":
                nv[path]+=1;last[path]=i
            elif kind=="edit":ne[path]+=1
    assert set(feat)==set(old)
    put(D/"features-seal.json",dict(rows=put(D/"features.json.gz",feat),history=put(D/"history.json.gz",hist),protocol=sha(D/"PROTOCOL_RU.md"),code=sha(Path(__file__)),
        source_manifest=sha(P/"manifest.json"),native_events=sha(V/"events.json.gz"),feature_names=NAMES))
if __name__=="__main__":prepare()
