from pathlib import Path
import hashlib,io,json,urllib.request,zipfile
R=Path(__file__).resolve().parent
base="https://api.github.com/repos/ojuschugh1/sqz"
def load(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"memory-research-readonly"}),timeout=45).read()
tag="v2.2.0"
release=json.loads(load(base+"/releases/tags/"+tag))
commit=json.loads(load(base+"/commits/"+tag))["sha"]
asset=next(a for a in release["assets"] if a["name"]==f"sqz-{tag}-x86_64-pc-windows-msvc.zip")
data=load(asset["browser_download_url"])
digest=lambda b:hashlib.sha256(b).hexdigest()
assert "sha256:"+digest(data)==asset["digest"]
folder=R/"vendor";folder.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(data)) as z:
    exe=z.read(next(n for n in z.namelist() if n.endswith("sqz.exe")));(folder/"sqz.exe").write_bytes(exe)
source=load("https://codeload.github.com/ojuschugh1/sqz/zip/"+commit)
with zipfile.ZipFile(io.BytesIO(source)) as z:
    for n in z.namelist():
        name=n.partition("/")[2]
        if not(name.startswith(("sqz/src/","sqz_engine/src/","sqz-mcp/src/","docs/src/")) or name in ["README.md","LICENSE-MIT","LICENSE-APACHE"]) or n.endswith("/"):continue
        target=folder/"src"/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n))
(R/"upstream.json").write_text(json.dumps(dict(tag=tag,commit=commit,url=asset["browser_download_url"],release_sha=digest(data),exe_sha=digest(exe),source_zip_sha=digest(source)),indent=2),encoding="utf8")
