"""Obtain official octofs Linux release and the Alpine tracing tool into this experiment only."""
import hashlib, io, json, tarfile, urllib.request
from pathlib import Path
D=Path(__file__).resolve().parent;v=D/"vendor";v.mkdir(exist_ok=True)
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"open-local-artifact-check"}),timeout=40) as t:return t.read()
def h(b):return hashlib.sha256(b).hexdigest()
def extract(raw,path):
    t=tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz",ignore_zeros=True)
    m=next(m for m in t if m.isfile() and (m.name==path or m.name.endswith("/"+path)))
    return t.extractfile(m).read()
repo=json.loads(get("https://api.github.com/repos/Muvon/octofs/releases/tags/0.25.2"))
asset=next(a for a in repo["assets"] if a["name"].endswith("x86_64-unknown-linux-musl.tar.gz"))
arc=get(asset["browser_download_url"]);assert asset["digest"]=="sha256:"+h(arc)
exe=extract(arc,"octofs");(v/"octofs").write_bytes(exe)
pkgroot="https://dl-cdn.alpinelinux.org/alpine/v3.22/main/x86_64/"
index=extract(get(pkgroot+"APKINDEX.tar.gz"),"APKINDEX").decode()
entry=next(r for r in index.split("\n\n") if "\nP:strace\n" in "\n"+r+"\n")
fields=dict(x.split(":",1) for x in entry.splitlines())
url=pkgroot+"strace-"+fields["V"]+".apk";apk=get(url);st=extract(apk,"usr/bin/strace");(v/"strace").write_bytes(st)
(D/"linux_sources.json").write_text(json.dumps({"octofs":{"url":asset["browser_download_url"],"archive":h(arc),"exe":h(exe),"digest":asset["digest"]},"strace":{"url":url,"index_record":entry,"archive":h(apk),"exe":h(st)}},indent=1))
