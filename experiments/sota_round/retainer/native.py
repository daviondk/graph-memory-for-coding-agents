"""Prepare native and range binary inputs; run in-process compiled external cache and score."""
import gzip
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from compression import zstd
import numpy as np
from study import HERE,RAW,RESULTS,LRU,S3FIFO,read_ranges,summarize
from fetch import byte_range,digest
import struct,zlib

DTYPE=np.dtype([("time","<u4"),("oid","<u8"),("size","<u4"),("next","<i8")])
PAIR=np.dtype([("oid","<u8"),("count","<u4")])

def transport(cmd):
    if os.name!="nt": return cmd
    return ["wsl","-d",os.environ.get("MSR_WSL","CodexX20MSR"),"--"]+[to_linux(x) if isinstance(x,Path) else x for x in cmd]

def to_linux(path):
    path=path.resolve()
    return "/mnt/"+path.drive[0].lower()+path.as_posix()[2:]

def run_s4(label,input_path,capacity,boundary,algo):
    label=label+"_"+algo
    stepfile=RAW/(label+".bin")
    ret=subprocess.run(transport([RAW/"s4driver",algo,str(capacity),str(boundary),input_path,stepfile]),capture_output=True,check=True)
    sf=np.fromfile(stepfile,dtype="<u4").reshape(-1,3)
    notes=ret.stderr.decode("utf8",errors="replace")
    matches=re.findall(r"totals n=(\d+) boundary=(\d+) miss_pre=(\d+) miss_post=(\d+)",notes)
    assert len(matches)==1
    n,cut,m_pre,m_post=map(int,matches[0])
    assert len(sf)+cut==n and sf[:,1].sum()==m_post
    d=summarize(sf)
    d.update(algo=algo,capacity=capacity,prefix_misses=m_pre,full_requests=n,run_log=notes.strip(),row_sha256=digest(sf.tobytes()))
    # Full native data are one request each, so a packed miss bit records the complete suffix.
    if label.startswith("native"):
        file=RESULTS/(label+".bits.gz")
        file.write_bytes(gzip.compress(np.packbits(sf[:,1].astype(bool),bitorder="little").tobytes(),mtime=0))
    else:
        (RESULTS/"steps"/(d["row_sha256"]+".gz")).write_bytes(gzip.compress(sf.tobytes(),mtime=0))
    return d

def object_replay(oids,pins,slots,kind,start):
    c=(S3FIFO(slots) if kind=="s3" else LRU(slots)) if slots else None
    miss=[0,0]; flags=np.zeros(len(oids)-start,np.uint8)
    for i,k in enumerate(oids):
        k=int(k)
        if k not in pins and (c is None or c.get(k) is None):
            miss[i>=start]+=1
            if i>=start:flags[i-start]=1
            if c is not None:c.put(k,True)
    return miss,flags

def native():
    buf=(RAW/"hm_native.zst").read_bytes()
    source=json.loads((HERE/"sources.json").read_text())
    assert digest(buf)==source["native_sha256"]
    b=zstd.decompress(buf);a=np.frombuffer(b,dtype=DTYPE)
    # Require the published object IDs to match raw CSV offsets, independently of filename.
    h=next(v for v in source["volumes"] if v["volume"]=="hm_0")
    off=h["zip_local_header"]; head=byte_range(off,off+511)
    values=struct.unpack_from("<4s5H3I2H",head)
    dataoff=off+30+values[-2]+values[-1]
    first=zlib.decompressobj(-15).decompress(byte_range(dataoff,dataoff+65535)).splitlines()[:1024]
    external=[tuple(map(int,l.split(b",")[4:6])) for l in first]
    assert [oid for oid,_ in external]==a["oid"][:len(first)].tolist()
    size_agreements=sum(size==published for (_,size),published in zip(external,a["size"].tolist()))
    oids=a["oid"];nt=len(a);cap=len(np.unique(oids))//10;warm=nt//5;fit=nt//10
    objects=np.ones(nt,dtype=PAIR);objects["oid"]=oids
    native_path=RAW/"native.stream";objects.tofile(native_path)
    d={"trace":"msr_hm_0.oracleGeneral.zst","records":nt,"unique":len(np.unique(oids)),"matched_raw_initial_offsets":len(first),"matching_sizes_in_initial_1024":int(size_agreements),"source_size_min":int(a["size"].min()),"source_size_max":int(a["size"].max()),"cap":cap,"warm":warm,"fit":fit,"methods":[]}
    def native_external(algo):return run_s4("native",native_path,cap,warm,algo)
    with ThreadPoolExecutor(3) as pool:d["methods"].extend(pool.map(native_external,("s4","lru","s3")))
    counts=Counter(map(int,oids[:fit]));freq=sorted(counts,key=lambda k:(-counts[k],k))
    trial={}
    for slots in (0,cap//2,cap):
        m,_=object_replay(oids[:warm],set(freq[:slots]),cap-slots,"s3",fit);trial[slots]=m[1]
    chosen=min(trial,key=trial.get)
    d["validation_native_misses"]=trial;d["selected_pin_slots"]=chosen
    counts=Counter(map(int,oids[:warm]));freq=sorted(counts,key=lambda k:(-counts[k],k))
    for label,slots,kind in [("reference_s3_python",0,"s3"),("reference_lru_python",0,"lru"),("static_joint_singleton",cap,"s3"),("half_pinned",cap//2,"s3"),("selected_pinned",chosen,"s3")]:
        pins=set(freq[:slots])
        m,flags=object_replay(oids,pins,cap-slots,kind,warm)
        bits=np.packbits(flags,bitorder="little").tobytes()
        (RESULTS/("native_"+label+".bits.gz")).write_bytes(gzip.compress(bits,mtime=0))
        d["methods"].append(dict(algo=label,capacity=cap,pins=len(pins),prefix_misses=m[0] if not slots else None,page_misses=m[1],full_requests=nt,n=nt-warm,bit_sha256=digest(bits)))
    (RESULTS/"native.json").write_text(json.dumps(d,indent=2),encoding="utf8")

def range_extra(v):
    ranges=read_ranges(v);name=v["volume"];rows=np.zeros(len(ranges),dtype=PAIR)
    rows["oid"]=[p.start for p in ranges];rows["count"]=[len(p) for p in ranges]
    file=RAW/(name+".stream");rows.tofile(file)
    result=run_s4("range_"+name,file,512,16384,"s4")
    result["volume"]=name
    return result

def main():
    source=json.loads((HERE/"sources.json").read_text())
    if sys.argv[-1]=="native":native()
    else:
        with ThreadPoolExecutor(3) as pool: r=list(pool.map(range_extra,source["volumes"]))
        (RESULTS/"range_s4.json").write_text(json.dumps(r,indent=2),encoding="utf8")
if __name__=="__main__":main()
