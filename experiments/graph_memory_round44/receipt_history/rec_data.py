from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent;PREV=HERE.parent/"history_writer"
sys.path.insert(0,str(PREV))
from common import *
from writer import Writer
from simulate import readback,match
MODES_R=("views","receipts","joint")
def store_file(n,v):
    p=HERE/n;b=(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)
def receipts(ob,labels):
    import re
    from examine import ROW,OMIT,R38_OMIT
    text="\n".join(x["text"] for x in ob["content"] if isinstance(x,dict) and isinstance(x.get("text"),str))
    if OMIT.search(text) or R38_OMIT.search(text):return [],"truncated"
    headers=0;active=False;address=[];rows={}
    for line in text.splitlines():
        if "cat -n" in line and line.rstrip().endswith("on a snippet of "+ob["path"]+":"):
            headers+=1;active=True;continue
        if not active:continue
        m=ROW.fullmatch(line)
        if not m:active=False;continue
        n=int(m[1]);address.append(n);rows[n]=m[2]
    if headers!=1 or not address:return [],"header"
    if address!=list(range(address[0],address[-1]+1)):return [],"gap"
    out=[]
    for n,dg in labels:
        if n not in rows or h(rows[n])!=dg:return [],"disagreement"
        out.append((n,dg,rows[n].encode()))
    return out,"accepted"

def prepare():
    import pyarrow.parquet as pq
    original=signed(PREV,"history-inputs.json.gz");events=original["events"];views=original["reads"];timeline=signed(H,"events.json.gz")
    requested=defaultdict(dict)
    for rid,frames in events.items():
        times={at for at,kind,path in frames if kind=="edit"}
        for ev in timeline[rid]["events"]:
            if ev[0] in times and ev[1]=="edit":
                at,_,path,details=ev[:4]
                if details["matched"]:requested[rid][at]=(h(path),details["rows"])
    del timeline
    import_bits={};admitted=defaultdict(dict);audit=Counter();hashes={}
    sys.path.insert(0,str(V))
    from examine import display
    for part in read(RAW/"files.json")["events"]:
        f=RAW/part["file"];assert sha(f)==part["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for k,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in hashes:hashes[run]=h(run)
                r=hashes[run]
                if r not in events:continue
                historic=views.get(r,{}).get(str(at))
                receipt=requested[r].get(at)
                if historic is None and receipt is None:continue
                raw=json.loads(batch.column(2)[k].as_py())["raw"]["observation"]
                ob={key:raw[key] for key in ("command","is_error","content","path")}
                if historic is not None:
                    assert receipt is None;values,_,_=display(ob)
                    for n,dg,size,ok in historic:
                        if ok:
                            body=values[n].encode();assert sha_bytes(body)==dg and len(body)==size
                            import_bits[dg]=body
                else:
                    assert ob["command"]=="str_replace" and not ob["is_error"]
                    path,labels=receipt;assert h(ob["path"].removeprefix("/testbed/").removeprefix("/workspace/"))==path
                    parsed,reason=receipts(ob,labels);audit[reason]+=1
                    if reason!="accepted":continue
                    rows=[]
                    for n,dg,body in parsed:
                        assert sha_bytes(body)==dg
                        if dg in import_bits:assert import_bits[dg]==body
                        import_bits[dg]=body;rows.append([n,dg,len(body),1])
                    admitted[r][at]=rows
    assert sum(map(len,requested.values()))==sum(audit.values())
    store_file("receipt-inputs.json.gz",admitted);store_file("input-seal.json",dict(receipts=sha(HERE/"receipt-inputs.json.gz"),
              counts=audit,all_receipt_rows=sum(len(v) for tbl in admitted.values() for v in tbl.values()),bound_source=sha(H/"events.json.gz"),
              previous=sha(PREV/"manifest.json"),projection_code=sha(HERE/"rec_data.py"),source=sha(RAW/"files.json")))
    return events,views,admitted,import_bits
def sha_bytes(body):return hashlib.sha256(body).hexdigest()
