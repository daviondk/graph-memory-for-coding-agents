import concurrent.futures,hashlib,json,sys,tarfile,urllib.request,zipfile
from pathlib import Path
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
D=Path(__file__).resolve().parent
specs={"tabulate":"0.10.0","markdown-it-py":"4.3.0","fsspec":"2026.9.0","networkx":"3.6.1","wcwidth":"0.9.4","linkify-it-py":"2.2.0","pydot":"4.0.1","lz4":"4.4.5","six":"1.17.0","mdurl":"0.1.2","uc-micro-py":"2.0.0","pyparsing":"3.3.2"}
consumers=["tabulate","markdown-it-py","networkx","fsspec"]
def get(url):
    with urllib.request.urlopen(url,timeout=50) as f:return f.read()
def choice(x):
    n,v=x;info=json.loads(get("https://pypi.org/pypi/"+n+"/"+v+"/json"));pref={tag:i for i,tag in enumerate(sys_tags())}
    whs=[a for a in info["urls"] if a["filename"].endswith(".whl") and (not a["requires_python"] or sys.version.split()[0] in SpecifierSet(a["requires_python"]))]
    compatible=[(min(pref[t] for t in tags&pref.keys()),a["filename"],a) for a in whs if (tags:=parse_wheel_filename(a["filename"])[3])&pref.keys()]
    if not compatible:raise ValueError((n,v,info["info"]["requires_python"]))
    desc=min(compatible)[2]
    def grab(a):
        dst=D/"sources"/a["filename"];dst.parent.mkdir(exist_ok=True)
        if not dst.is_file():dst.write_bytes(get(a["url"]))
        h=hashlib.sha256(dst.read_bytes()).hexdigest();assert h==a["digests"]["sha256"]
        return {"name":n,"version":v,"file":dst.name,"sha256":h,"url":a["url"]}
    ans=grab(desc)
    if n in consumers:
        sdist=next(a for a in info["urls"] if a["packagetype"]=="sdist")
        ans["sdist"]=grab(sdist);dst=D/"sources"/sdist["filename"]
        with tarfile.open(dst) as t:
            for member in t:
                rel=member.name.partition("/")[2];part=Path(rel)
                if not member.isfile() or ".." in part.parts or part.is_absolute() or not rel.endswith(".py") or not any(x.startswith("test") for x in part.parts):continue
                f=D/"upstream_tests"/n/part;f.parent.mkdir(exist_ok=True,parents=True)
                f.write_bytes(t.extractfile(member).read())
    return ans
if __name__=="__main__":
    pairs=list(specs.items())+[("tzdata",v) for v in ["2022.1","2022.2","2022.6","2022.7","2025.1","2025.2"]]
    with concurrent.futures.ThreadPoolExecutor(5) as ex:out=list(ex.map(choice,pairs))
    (D/"sources.lock.json").write_text(json.dumps(out,indent=2),encoding="utf8")
