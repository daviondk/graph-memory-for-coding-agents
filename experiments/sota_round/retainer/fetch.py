import concurrent.futures
import csv
import gzip
import hashlib
import io
import json
import os
import re
import struct
import sys
import urllib.request
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path(os.environ.get("MSR_CACHE_ROOT", "D:/CodexResearch/x20-msr-range"))
ARCHIVE = "https://s3.amazonaws.com/cache-datasets/cache_dataset_txt/2008_msr/msr.zip"
NATIVE = "https://s3.amazonaws.com/cache-datasets/cache_dataset_oracleGeneral/2007_msr/msr_hm_0.oracleGeneral.zst"
CODE = "https://raw.githubusercontent.com/cacheMon/py-cachemonCache/a0fff4e18c6a4af18c77bc8abca7ddd9e75b77c9/"
LIMIT = 32_768

def fetch(x):
    req = urllib.request.Request(x, headers={"User-Agent":"MSR-replay/1"})
    with urllib.request.urlopen(req,timeout=90) as r: return r.read()

def byte_range(start, end):
    req = urllib.request.Request(ARCHIVE, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req,timeout=90) as r:
        assert r.status==206 and r.headers["Content-Range"].startswith(f"bytes {start}-{end}/")
        return r.read()

def digest(buf):
    return hashlib.sha256(buf).hexdigest()

def members():
    q=urllib.request.Request(ARCHIVE,method="HEAD")
    with urllib.request.urlopen(q,timeout=45) as r:
        size=int(r.headers["Content-Length"]); etag=r.headers["ETag"]
    last=byte_range(size-65536,size-1)
    pos=last.index(b"PK\x01\x02"); members=[]
    while last[pos:pos+4]==b"PK\x01\x02":
        h=struct.unpack_from("<4s6H3I5H2I",last,pos); n,e,c=h[10:13]
        name=last[pos+46:pos+46+n].decode()
        extra=last[pos+46+n:pos+46+n+e]
        offset=h[-1]
        if offset==0xffffffff:
            while extra:
                tag,length=struct.unpack_from("<HH",extra)
                if tag==1:
                    skip=4+8*(int(h[9]==0xffffffff)+int(h[8]==0xffffffff))
                    offset=struct.unpack_from("<Q",extra,skip)[0];break
                extra=extra[4+length:]
            assert offset!=0xffffffff
        if re.fullmatch(r"msr/[a-z0-9]+_0\.csv",name):
            members.append((name,offset,h[8],h[7]))
        pos+=46+n+e+c
    return size,etag,members

def projected(info):
    name,offset,sz,crc=info
    local=byte_range(offset,offset+511)
    h=struct.unpack_from("<4s5H3I2H",local)
    assert h[0]==b"PK\x03\x04" and h[3]==8
    assert local[30:30+h[-2]].decode()==name
    start=offset+30+h[-2]+h[-1]
    dec=zlib.decompressobj(-15)
    entries=[]; tail=b""; readrows=0; rawrows=0; sha=hashlib.sha256()
    for pos in range(0,sz,1048576):
        packed=byte_range(start+pos,start+min(sz,pos+1048576)-1)
        lines=(tail+dec.decompress(packed)).split(b"\n");tail=lines.pop()
        for line in lines:
            row=line.rstrip(b"\r").split(b",")
            if len(row)<7: continue
            sha.update(line+b"\n");rawrows+=1
            stamp,host,disk,op,off,size,_=row
            if op==b"Read":
                entries.append(b",".join((stamp,off,size))+b"\n");readrows+=1
            else: assert op==b"Write"
            if readrows==LIMIT: break
        if readrows==LIMIT:break
    assert readrows>=1
    projection=b"".join(entries)
    target=RAW/(Path(name).stem+".csv.gz")
    target.write_bytes(gzip.compress(projection,mtime=0))
    return dict(volume=Path(name).stem,zip_member=name,zip_local_header=offset,zip_compressed_bytes=sz,zip_member_crc32=f"{crc:08x}",source_prefix_lines=rawrows,read_count=readrows,source_prefix_sha256=sha.hexdigest(),read_projection_sha256=digest(projection))

def main():
    RAW.mkdir(parents=True,exist_ok=True)
    size,etag,items=members()
    with concurrent.futures.ThreadPoolExecutor(6) as pool: d=list(pool.map(projected,items))
    src=HERE/"upstream";src.mkdir(exist_ok=True)
    code={}
    for fname,url in [("s3fifo.py",CODE+"src/cachemonCache/cache/s3fifo.py"),("cache.py",CODE+"src/cachemonCache/cache/cache.py"),("LICENSE",CODE+"LICENSE")]:
        data=fetch(url);(src/fname).write_bytes(data);code[fname]={"url":url,"sha256":digest(data)}
    native=fetch(NATIVE);(RAW/"hm_native.zst").write_bytes(native)
    manifest={"archive":ARCHIVE,"zip_bytes":size,"etag":etag,"volumes":sorted(d,key=lambda r:r["volume"]),"upstream":code,"native_url":NATIVE,"native_sha256":digest(native)}
    (HERE/"sources.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
    print("Fetched",len(d),"volumes and native hm_0")
if __name__=="__main__":main()
