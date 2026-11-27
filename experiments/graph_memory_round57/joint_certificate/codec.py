"""Lossless per-request alternatives, including an equally compact archive representation."""
from collections import Counter
import zlib
from certificate import materialize,unpack
from run import HERE,PAIR,INPUTS,load,write

def var(n):
    result=bytearray()
    while n>=128:result.append(128+n%128);n//=128
    result.append(n)
    return result

def integer(stream):
    n=0;shift=0
    while True:
        b=next(stream);n|=(b&127)<<shift;shift+=7
        if b<128:return n

def deltas(ids):
    p=0;out=bytearray()
    for x in sorted(ids):
        out+=var(x-p);p=x
    return out

def events(sets):
    raw=var(len(sets))
    for e in sets:raw+=var(len(e))+deltas(e)
    stream=iter(raw);actual=[]
    for _ in range(integer(stream)):
        last=0;entry=[]
        for _ in range(integer(stream)):
            last+=integer(stream);entry.append(last)
        actual.append(entry)
    assert actual==[sorted(e) for e in sets] and list(stream)==[]
    return bytes(raw)

def packet(s,selected):
    raw=var(len(s));ix={j:i for i,j in enumerate(selected)}
    expect=[]
    for m,g in sorted(s.items()):
        header=[m,g.a,g.b,g.j,len(g.uv)]
        for v in header:raw+=var(v)
        p=0
        for x,(u,v) in sorted(g.uv.items()):
            raw+=var(x-p);p=x
            if max(u,v)<=14:raw.append(16*u+v)
            else:raw.append(255);raw+=var(u)+var(v)
        offsets=[ix[j] for j in g.offsets]
        for j in offsets:raw+=var(j)
        expect.append((header,sorted(g.uv.items()),offsets))
    it=iter(raw);rest=[]
    for _ in range(integer(it)):
        header=[integer(it) for i in range(5)];cells=[];last=0
        for _ in range(header[-1]):
            last+=integer(it);v=next(it)
            uv=divmod(v,16) if v!=255 else (integer(it),integer(it))
            cells.append((last,uv))
        rest.append((header,cells,[integer(it) for _ in range(header[3])] if header[0]>2 else []))
    assert expect==rest and not list(it)
    return bytes(raw)

def main():
    audit=load(HERE/"queries.json.gz");out={}
    for label,file in INPUTS.items():
        gold=load(PAIR/(label+"-queries.json.gz"));sums=Counter()
        for repo,stream in load(file).items():
            ids={};by_sha={};archive={};calls={r["t"]:r for r in gold[repo]};saved={r["t"]:r for r in audit[label][repo]}
            for t,(sha,raw) in enumerate(stream):
                ps=raw if len(raw)<=64 else []
                if t in calls:
                    row=calls[t];a,b=(ids.get(p,-1) for p in row["seeds"])
                    selected=[by_sha[k] for k in row["evidence"]]
                    summary,_=materialize(selected,archive,a,b)
                    pkg=packet(unpack(summary),selected) if selected else packet({},[])
                    whole=events([archive[k] for k in selected])
                    # Separate network response per data-dependent size-stratum read.
                    groups=saved[t]["opened"]
                    fetched=[archive[by_sha[k]] for k in saved[t]["read_sha"]]
                    partial=[events([e for e in fetched if len(e)==m]) for m in groups]
                    sums.update(dict(whole_bytes=len(whole),package_bytes=len(pkg),refined_bytes=sum(map(len,partial)),
                       whole_zlib=len(zlib.compress(whole)),package_zlib=len(zlib.compress(pkg)),
                       refined_zlib=sum(len(zlib.compress(p)) for p in partial)))
                enc=[ids.setdefault(p,len(ids)) for p in ps]
                if len(ps)>=2:by_sha[sha]=t;archive[t]=enc
        out[label]=dict(sums);print(label,sums)
    write(HERE/"codec-results.json",out,False)
if __name__=="__main__":main()
