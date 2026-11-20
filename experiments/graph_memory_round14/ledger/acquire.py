"""Acquire pinned public primary sources, genuine release binary and deterministic source fixtures."""
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import urllib.parse
import urllib.request
import zipfile

D=Path(__file__).resolve().parent
V=D/"vendor"
V.mkdir(exist_ok=True)
def h(b): return hashlib.sha256(b).hexdigest()
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"local-research-code-artifact-review"}),timeout=60) as f:
        return f.read()
def save(name,x): (D/name).write_text(json.dumps(x,indent=1,ensure_ascii=True),encoding="utf8")
REPO="https://api.github.com/repos/Muvon/octofs"
def release():
    record=json.loads(get(REPO+"/releases/tags/0.25.2"))
    refs=json.loads(get(REPO+"/commits/0.25.2"))
    asset=next(v for v in record["assets"] if v["name"].endswith("x86_64-pc-windows-msvc.zip"))
    zipdata=get(asset["browser_download_url"])
    assert asset["digest"]=="sha256:"+h(zipdata)
    z=zipfile.ZipFile(io.BytesIO(zipdata))
    exe=z.read(next(n for n in z.namelist() if n.lower().endswith("octofs.exe")))
    (V/"octofs.exe").write_bytes(exe)
    raw=get("https://codeload.github.com/Muvon/octofs/tar.gz/"+refs["sha"])
    t=tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz")
    root=V/"source";root.mkdir(exist_ok=True)
    for m in t.getmembers():
        work=m.name.split("/",1)[-1]
        if m.isfile() and (work.startswith("src/") or work in ("Cargo.toml","Cargo.lock","README.md","LICENSE")):
            f=root/work;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(t.extractfile(m).read())
    save("octofs_source.json",{"repository":REPO,"version":"0.25.2","sha":refs["sha"],"tag":record["html_url"],"published":record["published_at"],"asset":asset["browser_download_url"],"zip_sha256":h(zipdata),"exe_sha256":h(exe),"source_tar_sha256":h(raw)})
def sources():
    urls={"article":"https://arxiv.org/html/2608.00808v1","author":"https://zehaowang00.github.io/","author_repos":"https://api.github.com/users/zehaowang00/repos?per_page=100","hf":"https://huggingface.co/api/papers/2608.00808","github_title":"https://api.github.com/search/repositories?q="+urllib.parse.quote('"Turning Interaction History into Execution State"'),"github_id":"https://api.github.com/search/repositories?q="+urllib.parse.quote('"2608.00808" in:readme')}
    out={}
    for k,url in urls.items():
        try:
            data=get(url);text=data.decode();row={"url":url,"sha256":h(data),"bytes":len(data)}
            if k=="article":
                links=re.findall(r'href=["\']([^"\']+)',text);row["noninternal_artifact_links"]=[u for u in links if any(d in u.lower() for d in ("github","zenodo","figshare","anonymous.4open","huggingface","osf.io"))]
            if k=="author":
                i=text.lower().find("turning interaction history");row["publication_entry"]=re.sub("<[^>]+>"," ",text[i-45:i+220])
            if k=="author_repos":row["public_repositories"]=[q["full_name"] for q in json.loads(data)]
            if k=="hf":row["repository_metadata"]={k:v for k,v in json.loads(data).items() if k in ("githubRepo","githubStars","id","projectPage")}
            if k.startswith("github_"):row["n"]=json.loads(data)["total_count"];row["repos"]=[q["full_name"] for q in json.loads(data)["items"][:20]]
            out[k]=row
        except OSError as e:out[k]={"url":url,"error":str(e)}
    save("ledger_audit.json",out)
def fixtures():
    pkgs=[("pallets/click","8.1.7","src/click/"),("python-attrs/attrs","24.2.0","src/attr/"),("HypothesisWorks/hypothesis","hypothesis-python-6.112.0","hypothesis-python/src/hypothesis/"),("yaml/pyyaml","6.0.2","lib/yaml/")]
    (D/"fixtures").mkdir(exist_ok=True);out=[]
    for repo,tag,prefix in pkgs:
        url="https://codeload.github.com/"+repo+"/tar.gz/refs/tags/"+tag
        raw=get(url);t=tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz");eligible=[];licenses=[]
        for m in t.getmembers():
            p=m.name.partition("/")[2]
            if not m.isfile():continue
            if p.lower() in ("license","license.rst","license.md","license.txt","license.apache2","license.mit","copying"):licenses.append((p,t.extractfile(m).read()))
            if not p.startswith(prefix) or not p.endswith(".py") or "test" in p.lower().split("/"):continue
            b=t.extractfile(m).read()
            try:text=b.decode("utf8")
            except UnicodeDecodeError:continue
            if "\r" in text or "\t" in text or not 30<=len(text.splitlines())<=180 or not text.endswith("\n"):continue
            eligible.append((h((repo+"/"+p).encode()),p,b))
        chosen=[]
        for _,p,b in sorted(eligible)[:3]:
            f=D/"fixtures"/repo.replace("/","__")/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
            chosen.append({"path":p,"fixture":f.relative_to(D).as_posix(),"sha256":h(b),"bytes":len(b),"lines":len(b.splitlines())})
        for p,b in licenses:
            f=D/"fixtures"/repo.replace("/","__")/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
        out.append({"repo":repo,"tag":tag,"url":url,"source_sha256":h(raw),"eligible":len(eligible),"chosen":chosen,"licenses":[p for p,_ in licenses]})
    save("fixtures.json",out)
if __name__=="__main__":
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        for future in [pool.submit(f) for f in (release,sources,fixtures)]:future.result()
