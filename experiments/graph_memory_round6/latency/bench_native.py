"""Replay the official symmetric archive and measure the two paths returning identical wire bytes."""
import base64,collections,ctypes as C,ctypes.util,gzip,hashlib,json,platform,statistics,sys,time
from pathlib import Path
from rendered import decode_output
D=Path(__file__).resolve().parent;P=D.parent/"published"
sys.path[:0]=[str(P),str(P/".linux-deps")]
import native,multiple,hybrid,symmetry_run
ARCHIVE=multiple.retrieve_many
Z=C.CDLL(ctypes.util.find_library("zstd"))
def bind(name,restype,args):
    fn=getattr(Z,name);fn.restype=restype;fn.argtypes=args;return fn
ptr=C.c_void_p;size=C.c_size_t
ctx=bind("ZSTD_createDCtx",ptr,[])()
dec=bind("ZSTD_decompress_usingDict",size,[ptr,ptr,size,ptr,size,ptr,size])
length=bind("ZSTD_getFrameContentSize",C.c_ulonglong,[ptr,size])
error=bind("ZSTD_isError",C.c_uint,[size])
dictionary=(D.parents[1]/"graph_memory_round4/writer/python_prior.bin").read_bytes()
def wire(q,ls):return hybrid.wire(q,ls).encode()
def hot(blob,q):
    assert len(blob)<=4096 and blob[1:4]==b"R5\x0a"
    s=blob[4:];n=length(s,len(s));assert n<5_000_000
    buf=C.create_string_buffer(n);size_out=dec(ctx,buf,n,s,len(s),dictionary,len(dictionary))
    assert not error(size_out) and size_out==n
    state=json.loads(buf.raw);assert state[1]==q["t"]
    result=[None]*q["n"];st=q["lo"];end=st+q["n"]
    for p,info,runs in state[2]:
        if p==q["path"]:
            for lo,_,texts in runs:
                a=max(lo,st);b=min(lo+len(texts),end)
                if b>a:result[a-st:b-st]=texts[a-lo:b-lo]
            break
    return result
def archive(call):
    q=call[3];raw=ARCHIVE(*call)
    blocks={r["step"]:decode_output(r["rendered"],q["path"],q["lo"],q["n"]) for r in raw["reads"]}
    return wire(q,[blocks[owner][j] if owner in blocks else None for j in range(q["n"]) for owner in [raw["owners"].get(q["lo"]+j)]])
def routed(call,mode="r5"):
    q=call[3];lines=hot(blobs[q["id"],q["t"]][mode],q)
    if all(s is not None for s in lines):
        payload=wire(q,lines)
        if len(payload)<=98304:return payload
    return archive(call)
def timed(*call):
    q=call[3];key=q["key"];row={"key":key,"id":q["id"],"repo":q["repo"],"us":{"archive":[],"routed":[],"lru":[]}}
    functions={"archive":archive,"routed":routed,"lru":lambda call:routed(call,"lru")};truth=wire(q,expected[key])
    row["hot"]=all(x is not None for x in hot(blobs[q["id"],q["t"]]["r5"],q))
    order=sorted(functions,key=lambda k:hashlib.sha256((key+"|"+k).encode()).hexdigest())
    for rep in range(4):
        for k in (order[rep%3:]+order[:rep%3]):
            start=time.perf_counter_ns();response=functions[k](call);dur=(time.perf_counter_ns()-start)/1000
            assert response==truth,key
            if rep:row["us"][k].append(dur)
    log.write(json.dumps(row)+"\n");log.flush()
    return None
def rows(p):
    with gzip.open(p,"rt",encoding="utf8") as f:yield from map(json.loads,f)
if __name__=="__main__":
    names=["bench_native.py","rendered.py","PROTOCOL_RU.md","NATIVE_RU.md"];lock={k:hashlib.sha256((D/k).read_bytes()).hexdigest() for k in names}
    for k in ["symmetry_run.py","multiple.py","native.py","external/symmetric_stream.jsonl.gz","external/queries.jsonl.gz","external/symmetric_oracle.jsonl.gz"]:lock[k]=hashlib.sha256((P/k).read_bytes()).hexdigest()
    blobfile=D.parent/"version/states_external_0.gz";lock["states_external_0.gz"]=hashlib.sha256(blobfile.read_bytes()).hexdigest();lock["python_prior.bin"]=hashlib.sha256(dictionary).hexdigest();lock["platform"]=platform.platform()
    (D/"native_lock.json").write_text(json.dumps(lock,indent=2))
    qindex=collections.defaultdict(list)
    for q in native.rows("external/queries.jsonl.gz"):qindex[q["id"]].append(q)
    expected=dict(native.rows("external/symmetric_oracle.jsonl.gz"))
    wanted={(q["id"],q["t"]) for qs in qindex.values() for q in qs}
    blobs={(i,t):{m:base64.b64decode(s[m]) for m in ("r5","lru")} for i,t,s,_ in rows(blobfile) if (i,t) in wanted}
    assert set(blobs)==wanted
    for key in list(qindex):qindex[key]=[q for q in qindex[key] if q["kind"]=="edit"]
    multiple.retrieve_many=timed;hybrid.choose=lambda *args:None
    dbdir=Path("/var/tmp/x20-r6-symmetric-memtrace-native-20261119");dbdir.mkdir(exist_ok=False)
    with (D/"times_native.jsonl").open("x",encoding="utf8") as log:
        for task in native.rows("external/symmetric_stream.jsonl.gz"):
            if qindex[task["id"]]:
                receipt,_=symmetry_run.process((task,qindex[task["id"]],dbdir));print(task["id"],len(qindex[task["id"]]),flush=True)


