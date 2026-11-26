"""Typed packet transport with literal fallback for an exactly recoverable digest."""
from io import BytesIO
from statistics import median
from time import perf_counter_ns
import re
from wire import *
PROTO="d52e07ae19b1e40fa1f0ae7d7112448b96373b36e94bae1932544eda4b274f10"
ID=re.compile("evidence-([0-9a-f]{24})")
SHA=re.compile("[0-9a-f]{64}")

def u(n):
    assert 0<=n<2**32
    chunks=bytearray()
    while n>=128:
        chunks.append((n&127)|128)
        n >>= 7
    chunks.append(n)
    return bytes(chunks)

def get_u(s):
    total=0
    for i in range(5):
        b=s.read(1)
        if len(b)!=1: raise ValueError("truncated integer")
        total |= (b[0]&127) << (7*i)
        if b[0]<128: return total
    raise ValueError("integer exceeds protocol limit")

def scalar(x):
    if x is None: return b"N"
    if type(x)==int and x>=0: return b"I"+u(x)
    if type(x)==str:
        v=x.encode("utf8")
        return b"S"+u(len(v))+v
    raise ValueError(f"unsupported scalar {type(x)}")

def get_scalar(s):
    tag=s.read(1)
    if tag==b"N": return None
    if tag==b"I": return get_u(s)
    if tag!=b"S": raise ValueError("invalid scalar")
    size=get_u(s);v=s.read(size)
    if len(v)!=size: raise ValueError("truncated text")
    return v.decode("utf8")

def eid(x):
    m=ID.fullmatch(x) if isinstance(x,str) else None
    return b"B"+bytes.fromhex(m[1]) if m else b"V"+scalar(x)

def get_id(s):
    tag=s.read(1)
    if tag==b"B": return "evidence-"+s.read(12).hex()
    if tag==b"V": return get_scalar(s)
    raise ValueError("invalid identity")

def derivable(digest, text):
    return isinstance(text,str) and isinstance(digest,str) and hashlib.sha256(text.encode("utf8")).hexdigest()==digest

def digest_field(h,txt,derive):
    if derive and derivable(h,txt): return b"F"
    if isinstance(h,str) and SHA.fullmatch(h): return b"B"+bytes.fromhex(h)
    return b"V"+scalar(h)

def read_digest(s,text,derive):
    t=s.read(1)
    if t==b"F" and derive: return hashlib.sha256(text.encode("utf8")).hexdigest()
    if t==b"B": return s.read(32).hex()
    if t==b"V": return get_scalar(s)
    raise ValueError("invalid digest")

def binary(rows,prev,derive):
    body={}
    full={}
    for i,r in enumerate(prev):
        body.setdefault(tuple(r[1:]),i);full.setdefault(tuple(r),i)
    buf=bytearray(u(len(rows)))
    for r in rows:
        if tuple(r) in full:
            buf.extend(b"R"+u(full[tuple(r)]))
        elif tuple(r[1:]) in body:
            buf.extend(b"B"+u(body[tuple(r[1:])])+eid(r[0]))
        else:
            buf.extend(b"L"+eid(r[0]))
            for j in (1,2,3,4,6): buf.extend(scalar(r[j]))
            buf.extend(digest_field(r[5],r[6],derive))
    return bytes(buf)

def read_binary(data,prev,derive):
    s=BytesIO(data);rows=[]
    for _ in range(get_u(s)):
        tag=s.read(1)
        if tag==b"R": row=prev[get_u(s)]
        elif tag==b"B":
            p=get_u(s);row=[get_id(s),*prev[p][1:]]
        elif tag==b"L":
            name=get_id(s);typ,path,first,last,txt=[get_scalar(s) for _ in range(5)]
            row=[name,typ,path,first,last,read_digest(s,txt,derive),txt]
        else: raise ValueError("invalid row")
        rows.append(row)
    if s.read(1): raise ValueError("trailing output")
    return rows

def binary_dictionary(prev):
    return zstd.ZstdDict(binary(prev,[],False),is_raw=True) if prev else None

def selected_encode(rows,prev,i):
    if i in (5,17): return encode(rows,prev,[i])[i]
    assert i in (24,25)
    return bytes([i])+zstd.compress(binary(rows,prev,i==25),level=19,zstd_dict=binary_dictionary(prev))

def selected_decode(frame,prev):
    i=frame[0]
    if i in (5,17): return decode(frame,prev)
    assert i in (24,25)
    return read_binary(zstd.decompress(frame[1:],zstd_dict=binary_dictionary(prev)),prev,i==25)

def aggregate(ins,qs,rows):
    repos=sorted({ins[q]["repo"] for q in qs})
    sums=np.zeros((len(repos),12))
    for q in qs:
        r=rows[q]
        sums[repos.index(ins[q]["repo"])]+=r["bytes"]+[median(a) for a in r["encode_ns"]]+[median(a) for a in r["decode_ns"]]
    bs=np.random.default_rng(510313).multinomial(len(repos),np.full(len(repos),1/len(repos)),size=20000)@sums
    total=sums.sum(0);out={}
    for nm,a,b in [("digest vs typed",2,3),("typed digest vs previous JSON",1,3),("slot JSON vs plain JSON",0,1)]:
        out[nm]={}
        for metric,offset in [("bytes",0),("encode",4),("decode",8)]:
            aa=a+offset;bb=b+offset
            out[nm][metric]=dict(totals=total[[aa,bb]].tolist(),ratio=total[bb]/total[aa],
                 ci_ratio=np.quantile(bs[:,bb]/bs[:,aa],[.025,.975]).tolist())
    return dict(states=len(qs),repos=len(repos),contrasts=out,derivable=sum(rows[q]["derivable"] for q in qs),
                fragments=sum(rows[q]["count"] for q in qs))

def main():
    assert sha(HERE/"COLUMNS_PROTOCOL_RU.md")==PROTO
    wire=read(HERE/"wire-results.json");assert wire["fixed_dev"]==[5,17]
    ins=read(HERE/"inputs.json.gz");caps=capsules(ins)
    # Probe both the fallback and the functional-dependency branch independently of the corpus.
    test=[["literal",None,"file",1,2,"not a digest","text"],["evidence-"+"a"*24,"repo","δ",1,7,hashlib.sha256(b"d").hexdigest(),"d"]]
    for i in (5,17,24,25):
        for prev,rows in (([],test),(test,[test[0],["different",*test[1][1:]]])):
            assert selected_decode(selected_encode(rows,prev,i),prev)==rows
    result={}
    ids=(5,17,24,25)
    qs=[q for q,z in ins.items() if z["panel"]=="outside"]
    for q in sorted(qs,key=lambda q:key(["shuffle",q])):
        rows=caps[q];prev=caps.get(ins[q]["parent"],[])
        assert all(len(r)==7 for r in rows)
        sizes={};hashes={};enc={i:[] for i in ids};dec={i:[] for i in ids}
        # Per-state pre-warm; measure wall time inside a single paired process.
        for i in ids:
            frame=selected_encode(rows,prev,i);sizes[i]=len(frame);hashes[i]=hashlib.sha256(frame).hexdigest()
            assert selected_decode(frame,prev)==rows
        for rep in range(7):
            for i in sorted(ids,key=lambda i:key([q,rep,i])):
                start=perf_counter_ns();f=selected_encode(rows,prev,i);encoded=perf_counter_ns()
                decoded=selected_decode(f,prev);ended=perf_counter_ns()
                assert len(f)==sizes[i] and decoded==rows
                enc[i].append(encoded-start);dec[i].append(ended-encoded)
        result[q]=dict(bytes=[sizes[i] for i in ids],hashes=[hashes[i] for i in ids],encode_ns=[enc[i] for i in ids],decode_ns=[dec[i] for i in ids],
            derivable=sum(derivable(r[5],r[6]) for r in rows),count=len(rows))
    summary={"outside":aggregate(ins,qs,result),"outside_warm":aggregate(ins,[q for q in qs if ins[q]["parent"]],result)}
    save("column-records.json.gz",result)
    save("column-results.json",dict(panels=summary,code=sha(HERE/"columns.py"),protocol=PROTO,records=sha(HERE/"column-records.json.gz"),
          wire=sha(HERE/"wire-results.json"),modes=ids,roundtrips=len(qs)*len(ids)*8,versions=wire["versions"]))
    print(json.dumps(summary))
if __name__=="__main__":
    main()

