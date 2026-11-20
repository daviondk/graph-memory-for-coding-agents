"""Fetch and pin document inputs; never import, install or execute release code."""
from pathlib import Path,PurePosixPath
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
import gzip,hashlib,io,json,re,tarfile,tomllib,urllib.request,zipfile
from packaging.version import Version, InvalidVersion
from packaging.utils import canonicalize_name
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/"downloads"
PROJECTS="attrs Babel click iniconfig more-itertools networkx packaging pluggy pyparsing python-dateutil tqdm wcwidth".split()
YEARS=(2022,2023,2024,2025)
FACETS=("summary","python","extras","direct")
def sha(b):return hashlib.sha256(b).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,x):
    b=json.dumps(x,ensure_ascii=False,sort_keys=True,indent=None if p.suffix==".gz" else 2).encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def fetch(url):return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"memory-document-research/1 (offline metadata verification)"}),timeout=45).read()
def lock_project(name):
    index=fetch("https://pypi.org/pypi/"+name+"/json")
    info=json.loads(index);years={}
    for yr in YEARS:
        cutoff=f"{yr}-06-30T23:59:59.999999Z";candidates=[]
        for v,files in info["releases"].items():
            try:version=Version(v)
            except InvalidVersion:continue
            if version.is_prerelease or version.is_devrelease:continue
            eligible=[f for f in files if not f["yanked"] and f["upload_time_iso_8601"]<=cutoff]
            binary=[f for f in eligible if f["filename"].lower().endswith("-none-any.whl")]
            sd=[f for f in eligible if f["packagetype"]=="sdist" and f["filename"].lower().endswith((".tar.gz",".zip"))]
            if binary and sd:
                b=min(binary,key=lambda f:(not f["filename"].endswith("-py3-none-any.whl"),f["filename"]))
                s=min(sd,key=lambda f:f["filename"]);candidates.append((version,v,b,s))
        if not candidates:continue
        _,v,b,s=max(candidates,key=lambda item:item[0])
        def pin(f):return {"filename":f["filename"],"url":f["url"],"sha256":f["digests"]["sha256"],"size":f["size"],"uploaded":f["upload_time_iso_8601"]}
        years[str(yr)]={"version":v,"wheel":pin(b),"sdist":pin(s)}
    return name,{"index_sha":sha(index),"snapshots":years}
def cache(p):
    path=CACHE/p["filename"]
    b=path.read_bytes() if path.exists() else fetch(p["url"])
    assert len(b)==p["size"] and sha(b)==p["sha256"],p["filename"]
    if not path.exists():path.write_bytes(b)
    return b
def main():
    CACHE.mkdir(exist_ok=True)
    with ThreadPoolExecutor(8) as ex:projects=dict(ex.map(lock_project,PROJECTS))
    put(ROOT/"releases.json",projects)
    unique={}
    for rec in projects.values():
        for version in rec["snapshots"].values():
            for kind in ("sdist","wheel"):
                f=version[kind];unique[f["filename"]]=f
    with ThreadPoolExecutor(8) as ex:
        for _ in ex.map(cache,unique.values()):pass
    print("projects",len(projects),"archives",len(unique),"bytes",sum(f["size"] for f in unique.values()),flush=True)

def python_spec(s):
    return str(SpecifierSet(s)) if s else None
def direct(seq):
    user=[Requirement(s) for s in seq]
    return sorted({canonicalize_name(req.name) for req in user if req.marker is None})
def source_fields(py):
    obj=tomllib.loads(py.decode()) if py else {};proj=obj.get("project",{});dyn=set(proj.get("dynamic",[]))
    if not proj:return {k:None for k in FACETS}
    result={}
    for facet,key in zip(FACETS,("description","requires-python","optional-dependencies","dependencies")):
        v=proj.get(key)
        if key in dyn:result[facet]=None
        elif facet=="summary":result[facet]=" ".join(v.split()) if v else None
        elif facet=="python":result[facet]=python_spec(v)
        elif facet=="extras":result[facet]=sorted({canonicalize_name(e) for e in (v or {})})
        else:result[facet]=direct(v or [])
    return result
def published(data):
    m=BytesParser().parsebytes(data)
    return dict(summary=" ".join(str(m["Summary"]).split()) if m["Summary"] else None,python=python_spec(m["Requires-Python"]),
                extras=sorted({canonicalize_name(e) for e in m.get_all("Provides-Extra",[])}),
                direct=direct(m.get_all("Requires-Dist",[])))
def wheel(entry):
    with zipfile.ZipFile(io.BytesIO(cache(entry))) as z:
        ns=[n for n in z.namelist() if n.endswith(".dist-info/METADATA")];assert len(ns)==1
        b=z.read(ns[0])
        return dict(fields=published(b),member=ns[0],member_bytes=len(b),member_sha=sha(b),wheel_sha=entry["sha256"])
def sources(entry):
    raw=cache(entry)
    if entry["filename"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members={n.rsplit("/",1)[1]:z.read(n) for n in z.namelist() if len(PurePosixPath(n).parts)==2 and PurePosixPath(n).name in ("pyproject.toml","PKG-INFO")}
    else:
        with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as z:
            members={PurePosixPath(x.name).name:z.extractfile(x).read() for x in z if x.isfile() and len(PurePosixPath(x.name).parts)==2 and PurePosixPath(x.name).name in ("pyproject.toml","PKG-INFO")}
    py=members.get("pyproject.toml");pi=members.get("PKG-INFO")
    return dict(py_sha=sha(py) if py is not None else None,py_bytes=len(py or b""),fields=source_fields(py),
                pkg_info=published(pi) if pi is not None else None,pkg_info_bytes=len(pi or b""),pkg_info_sha=sha(pi) if pi is not None else None)
if __name__=="__main__":main()
