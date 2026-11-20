"""Extract original ranges from the official SWE-smith parquet for the frozen R3 demand cohort."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

D=Path(__file__).resolve().parent
W=D.parents[1];C=W/"graph_memory_round3"/"demand";P=W/"memory_session5/packets"
sys.path.insert(0,str(P))
import extract5 as e

def load_ranges(r,shard,idx,old):
    assert hashlib.sha256(r['messages'].encode()).hexdigest()==old['messages_sha']
    m=json.loads(r['messages'])
    if any(z['role']=='tool' for z in m):
        ev=e.native.convert(r,shard,idx)['events']
    else:
        ev=[];prev=None
        for z in m:
            if z['role']=='assistant':
                fs=list(re.finditer(r'<function=([\w.-]+)>(.*?)</function>',e.native.textparts(z.get('content')),re.S))
                if len(fs)==1:
                    n,body=fs[0].groups()
                    args={a:e.wrap(v) for a,v in re.findall(r'<parameter=([\w.-]+)>(.*?)</parameter>',body,re.S)}
                    prev=[n,args]
                else:prev=['unresolved',{}]
            if z['role']=='user' and prev is not None:ev.append([*prev,None]);prev=None
    assert len(ev)==len(old['events'])
    views={}
    for k,(raw,masked) in enumerate(zip(ev,old['events']),1):
        name,a,txt=masked
        if a.get("command")!="view":continue
        assert raw[0]==name and raw[1]["path"]==a["path"] and raw[1]["command"]=="view"
        vr=raw[1].get("view_range")
        if isinstance(vr,str):
            try:vr=json.loads(vr)
            except (TypeError,ValueError):vr="invalid"
        views[k]=vr
    return views
def main():
    out={};checks=[];ss=json.loads((P/"shards.json").read_bytes())
    for k,s in enumerate(ss):
        fname=e.OLD/".scratch"/Path(s["path"]).name
        with fname.open("rb") as file:
            value=hashlib.file_digest(file,"sha256").hexdigest()
        assert value==s["lfs"]["oid"]
        keep={r["row"]:r for r in (json.loads(q) for q in gzip.open(C/f"source_{k}.jsonl.gz","rb"))}
        pf=e.pq.ParquetFile(fname);idx=0
        for batch in pf.iter_batches(batch_size=24,columns=["instance_id","traj_id","model","messages"],use_threads=False):
            for j in range(batch.num_rows):
                if idx in keep:
                    old=keep[idx];r=batch.slice(j,1).to_pylist()[0]
                    assert r["instance_id"]==old["instance"] and r["traj_id"]==old["traj"]
                    out[old["instance"]]=load_ranges(r,k,idx,old)
                idx+=1
        pf.close()
        checks.append(dict(shard=k,sha256=value,rows=idx,traces=len(keep)))
        print(k,len(out),flush=True)
    assert len(out)==282
    (D/'range_C.json').write_text(json.dumps(out),encoding='utf8')
    (D/'source_C_receipt.json').write_text(json.dumps(checks,indent=1),encoding='utf8')
if __name__=="__main__":main()
