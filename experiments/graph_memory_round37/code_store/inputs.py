"""Extract prefix-only transitions and seal the independent reference."""
import json,gzip,hashlib
from pathlib import Path
from collections import Counter
D=Path(__file__).resolve().parent; P=D.parent/"code_visibility"
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def h(text):return hashlib.sha256(text.encode()).hexdigest()
def get(path):return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def put(path,x):
    raw=(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)
    return sha(path)
def cap(path,d,n=128):
    if len(d)<=n:return dict(d)
    return dict(sorted(d.items(),key=lambda pair:(h("R37-128|"+path+"|"+str(pair[0])),pair[0]))[:n])
def prepare():
    assert sha(P/"manifest.json")=="4ae0456b82d9c53d506a329f3882f202c2d99b7461580349a9c7f1a000e9b27f"
    sig=get(P/"manifest.json")["files"]
    for name in ("events.json.gz","predictions.json.gz"):assert sha(P/name)==sig[name]
    events={rid:{e[0]:e for e in row["events"]} for rid,row in get(P/"events.json.gz").items()}
    allq=get(P/"predictions.json.gz");inputs={};oracle={}
    for p in allq:
        a=events[p["rid"]][p["prev"]];b=events[p["rid"]][p["edit"]]
        assert a[0]<b[0] and a[1]=="read" and b[1]=="edit" and a[2]==b[2] and h(a[2])==p["path_hash"]
        path=a[2];change=b[3];start=change["k"];end=start+change["old_breaks"] if start is not None else None
        q=p["q"];assert q not in inputs
        inputs[q]=dict(issue=p["issue"],zone=p["cohort"]+"_"+p["window"],path=path,
            base=sorted(cap(path,dict(a[3])).items()),receipt=sorted(cap(path,dict(change["rows"])).items()),start=start,end=end,delta=change["delta"])
        oracle[q]=p["mem"]["T"]
    assert len(inputs)==1282
    panel=sorted(inputs,key=lambda q:h("R37-code-store|"+q))[:128]
    put(D/"plan.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),parent=sha(P/"manifest.json"),input=put(D/"prefix_inputs.json.gz",inputs),
        evaluator=put(D/"reference.json.gz",oracle),panel=panel,selection="R37-code-store|",prepare_code=sha(Path(__file__)),
        sqlite_code=sha(D/"storage.py"),benchmark_code=sha(D/"benchmark.py")))
if __name__=="__main__":prepare()
