"""Serialize alternative read addresses per already-visible line strictly from prefix."""
from collections import defaultdict
from time import perf_counter_ns
from pathlib import Path
import struct,gzip,hashlib,json
from inventory import P,D,save,get
ARMS=("one","first_two","latest","distinct_worker")
NULL=0xffffffff
def encode(cases):
    arrays={a:bytearray() for a in ARMS};keybuf=bytearray();full=bytearray();offsets={};timing=[]
    for r in cases:
        st=perf_counter_ns();ev=r["events"];sources=defaultdict(set)
        for i,e in enumerate(ev):
            for path,ls in e["r"]:
                for line,digest,_ in ls:sources[(path,line,digest)].add(i)
        keys=sorted(sources)
        first=len(keybuf)//68;fe=len(full);offsets[r["id"]]=dict(start=first,n=len(keys),full_start=fe,events=[e["w"] for e in ev]);n=0
        for path,ln,b in keys:
            keybuf.extend(bytes.fromhex(path)+struct.pack("<I",ln)+bytes.fromhex(b))
            ids=sorted(sources[(path,ln,b)]);fst=ids[0];remain=ids[1:];worker=ev[fst]["w"]
            second=remain[0] if remain else NULL
            options=(NULL,second,remain[-1] if remain else NULL,next((i for i in remain if ev[i]["w"]!=worker),second))
            for a,v in zip(ARMS,options):arrays[a].extend(struct.pack("<II",fst,v))
            full.extend(struct.pack("<I",len(ids)));full.extend(struct.pack("<"+"I"*len(ids),*ids));n+=len(ids)
        timing.append(dict(id=r["id"],keys=len(keys),receipt_visits=n,build_ns=perf_counter_ns()-st))
    return arrays,keybuf,full,offsets,timing
def writebyte(path,b):
    path.write_bytes(b);return dict(sha=hashlib.sha256(b).hexdigest(),raw=len(b),gzip_bytes=len(gzip.compress(b,mtime=0)))
def main(p):
    rows=get(P/(p+"-prefix.json.gz"));assert hashlib.sha256((P/(p+"-prefix.json.gz")).read_bytes()).hexdigest()==get(D/(p+"-projection.json"))["prefix_sha"]
    arts,keys,full,ofs,t=encode(rows);out={}
    for a,b in dict(arts,keys=keys,full=full).items():out[a]=writebyte(P/(p+"-"+a+".bin"),b)
    h=save(P/(p+"-offsets.json.gz"),ofs);trec=save(D/(p+"-build-cost.json.gz"),t)
    save(D/(p+"-forecast-seal.json"),dict(prefix=get(D/(p+"-projection.json"))["prefix_sha"],arrays=out,offsets=h,build=trec,code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()));print(p,len(rows),out["keys"]["raw"]//68)
if __name__=="__main__":
    import sys
    main(sys.argv[1])

