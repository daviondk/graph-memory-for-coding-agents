import hashlib,json,urllib.request,zipfile,shutil
from pathlib import Path
D=Path(__file__).resolve().parent/"native";D.mkdir(exist_ok=True)
tag="v0.36.0"
api=json.load(urllib.request.urlopen("https://api.github.com/repos/semlith/semlith/releases/tags/"+tag))
links={a["name"]:a for a in api["assets"]}
def get(name):return urllib.request.urlopen(links[name]["browser_download_url"],timeout=85).read()
sha=get("SHA256SUMS").decode();name=f"semlith-{tag}-x86_64-pc-windows-msvc.zip";h=next(s.split()[0] for s in sha.splitlines() if name in s)
f=D/name
if not f.exists():f.write_bytes(get(name))
assert hashlib.sha256(f.read_bytes()).hexdigest()==h
with zipfile.ZipFile(f) as z:
 for n in z.namelist():
  if not n.endswith("/") and n.lower().endswith((".exe",".dll")):
   dst=D/Path(n).name
   with z.open(n) as s,dst.open("wb") as w:shutil.copyfileobj(s,w)
(D/"release.json").write_text(json.dumps({"tag":tag,"url":links[name]["browser_download_url"],"sha256":h,"files":[p.name for p in D.iterdir()]},indent=2))
print(h)
