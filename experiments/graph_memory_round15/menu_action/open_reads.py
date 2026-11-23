"""Physically open every logical selection at the original repository base; this process opens no outcomes."""
import collections
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from menu import D,h,read,put,lock
MIRRORS = [Path("D:/CodexResearch/x20-round13-reformulation-objects"),
           Path("D:/CodexResearch/x20-round14-grounded-objects")]
def inspect(job):
    c,link,call=job;p=call["path"]
    result={"id":c["id"],"iid":c["iid"],"panel":c["panel"],"arm":link["arm"],"repo":c["repo"],"base":c["base"],"call":call["sha"],"path":p,
            "opened":False,"bytes":0,"source":None,"sha256":None,"blob":None}
    if not p:return result,None
    assert re.fullmatch("[0-9a-f]{40}",c["base"]) and not PurePosixPath(p).is_absolute() and ".." not in PurePosixPath(p).parts
    start=time.perf_counter();raw=None;errors=[]
    for folder in MIRRORS:
        mirror=folder/(c["repo"].replace("/","__")+".git")
        if not mirror.is_dir():continue
        r=subprocess.run(["git","-C",str(mirror),"cat-file","blob",c["base"]+":"+p],capture_output=True,timeout=25,
                         env={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_NO_LAZY_FETCH":"1"})
        if not r.returncode:raw=r.stdout;result["source"]="git cat-file "+str(folder.name);break
    if raw is None:
        url=f"https://raw.githubusercontent.com/{c['repo']}/{c['base']}/"+urllib.parse.quote(p)
        params=urllib.request.Request(url,headers={"User-Agent":"immutable-version-research-reader"})
        for k in range(2):
            try:
                with urllib.request.urlopen(params,timeout=22) as reply:
                    raw=reply.read()
                    result.update(source="immutable raw Git revision",response_content_type=reply.headers.get("Content-Type"))
                break
            except OSError as e:
                errors.append(str(e))
                if isinstance(e,urllib.error.HTTPError) and e.code==404:break
    result["seconds"]=time.perf_counter()-start
    if raw is None:result["error"]=errors;return result,None
    result.update(opened=True,bytes=len(raw),sha256=h(raw),blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest())
    return result,raw
def main():
    lock(D/"assignment.json");lock(D/"action.lock.json")
    cases={c["id"]:c for c in read(D/"menus.json.gz")};links=read(D/"logical_calls.json")
    calls={r["sha"]:r for r in (json.loads(v) for v in (D/"model_calls.jsonl").read_bytes().splitlines())}
    for r in calls.values():assert h(r["original_response"].encode())==r["response_sha"]
    jobs=[(cases[v["id"]],v,calls[v["sha"]]) for v in links]
    blobdir=D/"blobs";blobdir.mkdir(exist_ok=True);rs=[];sigs={}
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        for row,b in pool.map(inspect,jobs):
            rs.append(row)
            if b is None:continue
            p=blobdir/(h(b)+".gz")
            if p.exists():assert gzip.decompress(p.read_bytes())==b
            else:p.write_bytes(gzip.compress(b,mtime=0))
            sigs[p.relative_to(D).as_posix()]=h(p.read_bytes())
    assert len(rs)==len(jobs)
    put(D/"reads.json.gz",rs);put(D/"blob.lock.json",sigs)
    put(D/"read.lock.json",{n:h((D/n).read_bytes()) for n in ("action.lock.json","reads.json.gz","open_reads.py","blob.lock.json")})
    print("physical opened",sum(r["opened"] for r in rs),"/",len(rs),"unique bytestrings",len(sigs),flush=True)
if __name__=="__main__":main()
