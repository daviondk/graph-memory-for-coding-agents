"""Extract uninstalled Alpine strace libraries only. Do not alter the distribution."""
import io,json,tarfile
from get_linux import D,v,get,h,extract,pkgroot
index=extract(get(pkgroot+"APKINDEX.tar.gz"),"APKINDEX").decode()
records=[dict(x.split(":",1) for x in r.splitlines()) for r in index.strip().split("\n\n")]
need=["libdw.so.1"];done=set();out={};(v/"lib").mkdir(exist_ok=True)
while need:
    name=need.pop()
    if name in done or name.startswith("libc.musl") or name.startswith("ld-musl"):continue
    done.add(name)
    try:rec=next(r for r in records if any(z.split("=")[0]=="so:"+name for z in r.get("p","").split()))
    except StopIteration:
        out[name]={"system":True};continue
    url=pkgroot+rec["P"]+"-"+rec["V"]+".apk";raw=get(url)
    tar=tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz",ignore_zeros=True)
    target=next(m for m in tar.getmembers() if m.name.endswith("/"+name))
    if target.issym():target=next(m for m in tar.getmembers() if m.name.endswith("/"+target.linkname))
    z=tar.extractfile(target).read();(v/"lib"/name).write_bytes(z)
    out[name]={"pkg":rec["P"],"url":url,"sha":h(z),"apk_sha":h(raw)}
    need.extend(s[3:].split("=")[0] for s in rec.get("D","").split() if s.startswith("so:"))
(D/"trace_libs.json").write_text(json.dumps(out,indent=1))
