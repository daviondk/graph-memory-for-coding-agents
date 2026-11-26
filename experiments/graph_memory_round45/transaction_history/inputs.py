"""Replay visible confirmed editor actions and responses without using full revision contents."""
from pathlib import Path
import sys,time
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];R=ROOT/"graph_memory_round44/receipt_history"
sys.path.insert(0,str(R))
from rec_data import *
from mechanism import tokens as equality_tokens,project
import pyarrow.parquet as pq
def wr(n,v):
    p=OUT/n;b=(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix==".gz" else b)
def normalized(path):return h(path.removeprefix("/testbed/").removeprefix("/workspace/"))
def identity(v):return v if isinstance(v,str) and v else None
def full_display(ob):
    from examine import ROW
    text="\n".join(a["text"] for a in ob["content"] if isinstance(a,dict) and isinstance(a.get("text"),str));out={};active=False
    for s in text.splitlines():
        if "cat -n" in s and s.rstrip().endswith("on a snippet of "+ob["path"]+":"):active=True;continue
        if active:
            m=ROW.fullmatch(s)
            if m:out[int(m[1])]=m[2]
            else:active=False
    return out
def locate(rows,literal):
    if not rows or not literal:return None
    lo=min(rows);hi=max(rows);assert hi-lo+1==len(rows)
    text="\n".join(rows[i] for i in range(lo,hi+1));where=text.find(literal)
    if where<0 or text.find(literal,where+1)>=0:return None
    return lo+text.count("\n",0,where)
def collect():
    old=signed(PREV,"history-inputs.json.gz");frames=old["events"];vread=old["reads"];receipts=signed(R,"receipt-inputs.json.gz")
    wanted={r:{at:(kind,path) for at,kind,path in seq if kind in ("read","write_start","edit")} for r,seq in frames.items()}
    starts=defaultdict(dict);ends=defaultdict(dict);bodies={};memo={};types=Counter();sys.path.insert(0,str(V))
    from examine import display
    for p in read(RAW/"files.json")["events"]:
        f=RAW/p["file"];assert sha(f)==p["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for j,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in memo:memo[run]=h(run)
                rid=memo[run];entry=wanted.get(rid,{}).get(at)
                if not entry:continue
                kind,path=entry;raw=json.loads(batch.column(2)[j].as_py())["raw"]
                if kind=="write_start":
                    act=raw["action"];assert normalized(act["path"])==path
                    if act["command"]=="str_replace" and all(isinstance(act.get(k),str) for k in ("old_str","new_str")) and act["old_str"] and identity(raw.get("id")) and identity(raw.get("tool_call_id")):
                        starts[rid][at]=(path,raw["id"],raw["tool_call_id"],act["old_str"],act["new_str"])
                    types["write_start"]+=1;continue
                ob0=raw["observation"];ob={k:ob0[k] for k in ("command","path","is_error","content")};assert normalized(ob["path"])==path
                if kind=="read":
                    view,_,_=display(ob);which=vread[rid][str(at)]
                elif str(at) in receipts.get(rid,{}):
                    view=full_display(ob);which=receipts[rid][str(at)]
                    ends[rid][at]=(path,identity(raw.get("action_id")),identity(raw.get("tool_call_id")),view)
                else:continue
                for n,d,size,ok in which:
                    if ok:
                        b=view[n].encode();assert len(b)==size and hashlib.sha256(b).hexdigest()==d;bodies[d]=b
    wr("input-seal.json",dict(starts=sum(map(len,starts.values())),matched_observable_receipts=sum(map(len,ends.values())),types=types,
       history=sha(PREV/"manifest.json"),receipts=sha(R/"manifest.json"),raw=sha(RAW/"files.json"),code=sha(OUT/"inputs.py")))
    return frames,vread,receipts,starts,ends,bodies
