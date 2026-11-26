"""Decode-equivalent SERBench memory updates; exact byte counts include the one-byte format tag."""
from compression import zstd
from time import perf_counter_ns
from platform import python_version
import numpy as np
from common import *

WIRE_PLAN = "6803b5c503adf72a020abd6c2b419a49857e78a9519976c6f83c15b796c1d310"
FAMILIES = ("rows", "columns", "row_slots", "body_slots")
MODES = [(f,l,d) for f in FAMILIES for l in (3,9,19) for d in (False,True)]
FIELDS = ("evidence_id","source_type","source_path","line_start","line_end","content_sha256","content_excerpt")

def packed(obj):
    return json.dumps(obj,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf8")

def columns(rows):
    return [[row[0] for row in rows],[row[1:] for row in rows]]

def representation(rows, previous, family):
    if family == "rows":
        return rows
    ids,bodies=columns(rows)
    if family == "columns":
        return [ids,bodies]
    old_bodies={}
    old_rows={}
    for i,row in enumerate(previous):
        old_bodies.setdefault(tuple(row[1:]),i)
        old_rows.setdefault(tuple(row),i)
    if family=="body_slots":
        return [ids,[old_bodies.get(tuple(body),body) for body in bodies]]
    payload=[]
    for row in rows:
        if tuple(row) in old_rows:
            payload.append(old_rows[tuple(row)])
        elif tuple(row[1:]) in old_bodies:
            payload.append([row[0],old_bodies[tuple(row[1:])]])
        else:
            payload.append(row)
    return payload

def dictionary(previous,family):
    if not previous:
        return None
    x=previous if family in ("rows","row_slots") else columns(previous)
    return zstd.ZstdDict(packed(x),is_raw=True)

def encode(rows,previous,mode_ids):
    payload={}
    refs={}
    frames={}
    for tag in mode_ids:
        family,level,use_dictionary=MODES[tag]
        if family not in payload:
            payload[family]=packed(representation(rows,previous,family))
        if use_dictionary and family not in refs:
            refs[family]=dictionary(previous,family)
        frames[tag]=bytes([tag])+zstd.compress(payload[family],level=level,zstd_dict=refs.get(family) if use_dictionary else None)
    return frames

def decode(frame, previous):
    family,_,use_dictionary=MODES[frame[0]]
    ref=dictionary(previous,family) if use_dictionary else None
    payload=json.loads(zstd.decompress(frame[1:],zstd_dict=ref))
    if family=="rows":
        return payload
    if family=="row_slots":
        result=[]
        for row in payload:
            if isinstance(row,int):
                result.append(previous[row])
            elif len(row)==2:
                result.append([row[0],*previous[row[1]][1:]])
            else:
                result.append(row)
        return result
    ids,bodies=payload
    if family=="body_slots":
        bodies=[previous[v][1:] if isinstance(v,int) else v for v in bodies]
    return [[i,*b] for i,b in zip(ids,bodies,strict=True)]

def verify_small():
    a=["a","repo","path",1,2,"e","alpha"]
    b=["б","repo","path2",2,5,"x","δελτα"]
    c=["a2",*a[1:]]
    for before,after in (([],[]),([],[a,b]),([a,b],[b,c,a,a]),([a,c],[c,b]),([b],[a]),([a],[])):
        for f in encode(after,before,range(24)).values():
            assert decode(f,before)==after

def capsules(inputs):
    with gzip.open(UPSTREAM/"data/cal500/items.jsonl.gz","rt",encoding="utf8") as f:
        result={}
        for z in map(json.loads,f):
            q=z["state_id"]
            if q not in inputs:
                continue
            c=inputs[q]
            raw={v["evidence_id"]:v for v in z["candidate_evidence"]}
            result[q]=[[raw[c["ids"][i]].get(a) for a in FIELDS] for i in c["current"][:8]]
    assert result.keys()==inputs.keys()
    return result

def compare(inputs, outcomes, questions, fixed):
    qs=sorted(questions)
    repos=sorted({inputs[q]["repo"] for q in qs})
    sums=np.zeros((len(repos),4),dtype=np.int64)
    wins=[0,0]
    times=[[],[]]
    for q in qs:
        z=outcomes[q];n=z["bytes"]
        data=[min(n[:12]),min(n),n[fixed[0]],n[fixed[1]]]
        sums[repos.index(inputs[q]["repo"])]+=data
        wins[0]+=data[1]<data[0]
        wins[1]+=data[3]<data[2]
        for i in range(2): times[i].append(z["time_ns"][i])
    totals=sums.sum(0)
    boot=np.random.default_rng(510312).multinomial(len(repos),np.full(len(repos),1/len(repos)),size=20000)@sums
    pairs={}
    for j,a in enumerate(("portfolio","fixed")):
        base=2*j
        frac=(boot[:,base]-boot[:,base+1])/boot[:,base]
        pairs[a]=dict(bytes=totals[base:base+2].tolist(),strictly_improved=wins[j],relative=1-totals[base+1]/totals[base],
                      ci=np.quantile(frac,[.025,.975]).tolist())
    return dict(states=len(qs),repos=len(repos),contrasts=pairs,
                encoder_ms=[dict(mean=np.mean(t)/1e6,median=np.median(t)/1e6,p95=np.quantile(t,.95)/1e6) for t in times])

def main():
    assert sha(HERE/"WIRE_PROTOCOL_RU.md")==WIRE_PLAN
    assert sha(UPSTREAM/"data/cal500/items.jsonl.gz")==read(HERE/"input-seal.json")["sources"]["items"]
    verify_small()
    ins=read(HERE/"inputs.json.gz")
    caps=capsules(ins)
    output={}
    first=next(iter(caps.values()))
    encode(first,first,range(24))
    for q in sorted(ins,key=lambda a:key(["run",a])):
        rows=caps[q];prior=caps.get(ins[q]["parent"],[])
        # Warm up once globally. Alternate run order per state by a prospectively unrelated digest.
        order=(12,24) if int(key(["order",q])[-2:],16)%2 else (24,12)
        times={}
        lengths=None
        for n in order:
            start=perf_counter_ns()
            frames=encode(rows,prior,range(n))
            best=min(frames.values(),key=len)
            times[n]=perf_counter_ns()-start
            if n==24:
                lengths=[len(f) for f in frames.values()]
                hashes=[hashlib.sha256(f).hexdigest() for f in frames.values()]
                for f in frames.values():
                    assert decode(f,prior)==rows
        output[q]=dict(bytes=lengths,hashes=hashes,canonical_sha256=hashlib.sha256(packed(rows)).hexdigest(),
                       canonical_bytes=len(packed(rows)),time_ns=[times[12],times[24]],order=order)
    dev=[q for q,s in ins.items() if s["panel"]=="dev"]
    fixed=[min(r,key=lambda j:sum(output[q]["bytes"][j] for q in dev)) for r in (range(12),range(12,24))]
    result={}
    for panel in ("dev","outside"):
        qs=[q for q,s in ins.items() if s["panel"]==panel]
        result[panel]=compare(ins,output,qs,fixed)
        result[panel+"_warm"]=compare(ins,output,[q for q in qs if ins[q]["parent"]],fixed)
    save("wire-records.json.gz",output)
    save("wire-results.json",dict(panels=result,modes=MODES,fixed_dev= fixed,wire_protocol=WIRE_PLAN,code=sha(HERE/"wire.py"),
                                inputs=sha(HERE/"inputs.json.gz"),records=sha(HERE/"wire-records.json.gz"),
                                versions=dict(python=python_version(),zstd=zstd.zstd_version_info,numpy=np.__version__),
                                exact_decodes=24*len(ins),edge_decodes=24*6))
    print(json.dumps({k:v for k,v in result.items() if k.startswith("outside")},ensure_ascii=False),fixed)
if __name__=="__main__":
    main()

