"""Read only published metadata/model artifacts. No states or predictions are transmitted."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import gzip,io,json,tarfile,urllib.request as web
D=Path(__file__).resolve().parent
REV="8c27a88e48dcbcd4a5745573c95937a4740f4406"
HF="233902d25c440f23af6f7d6e94d2946bac0bee0a"
GH="https://api.github.com/repos/LordTARN1SHED/SERBench/"
RAW=f"https://raw.githubusercontent.com/LordTARN1SHED/SERBench/{REV}/"
def fetch(url):
    req=web.Request(url,headers={"User-Agent":"Code-memory-public-artifact-study"})
    with web.urlopen(req,timeout=60) as f:return f.read()
def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
def main():
    cache=D/"runtime";cache.mkdir(exist_ok=True)
    def model(name):
        data=fetch(f"https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/resolve/{HF}/"+name)
        (cache/Path(name).name).write_bytes(data);return name,sha256(data).hexdigest()
    objs=("onnx/model_quint8_avx2.onnx","tokenizer.json")
    with ThreadPoolExecutor(2) as ex: models=dict(ex.map(model,objs))
    tree=json.loads(fetch(GH+"git/trees/"+REV+"?recursive=1"))
    assert tree["sha"]==REV and not tree["truncated"]
    files={f["path"]:f for f in tree["tree"] if f["type"]=="blob"}
    results={}
    for name in sorted(files):
        if not name.startswith("reference_results/") or name.endswith("manifest.json"):continue
        data=fetch(RAW+name); content=json.loads(data);assert len(content)==1
        method,metrics=next(iter(content.items()))
        assert metrics["states"]==500 and all(isinstance(v,(float,int)) for v in metrics.values())
        results[method]=dict(at5=metrics["mss_complete@5"],at8=metrics["mss_complete@8"],
                             file=name,sha256=sha256(data).hexdigest())
    assert len(results)==12
    arxiv=fetch("https://arxiv.org/src/2609.20050v3")
    with tarfile.open(fileobj=io.BytesIO(arxiv),mode="r:gz") as t:
        members=[m.name for m in t.getmembers()]
    notes=json.loads(fetch("https://api2.openreview.net/notes/search?term=The%20Missing%20Complement&limit=5"))
    note=next(n for n in notes["notes"] if n["id"]=="07qozKbnPm")
    url="https://api2.openreview.net/attachment?id=07qozKbnPm&name=supplementary_material"
    try:
        response=web.urlopen(web.Request(url,headers={"Range":"bytes=0-511"}),timeout=20)
        status=response.status;failure=None;response.close()
    except web.HTTPError as exc:
        status=exc.code
        try:failure=json.loads(exc.read())["name"]
        except (KeyError,ValueError):failure="unclassified"
    info=dict(revision=REV,tree={k:v["sha"] for k,v in files.items()},reference=results,
              arxiv_members=members,arxiv_sha=sha256(arxiv).hexdigest(),
              release_tags=[r["tag_name"] for r in json.loads(fetch(GH+"releases"))],
              branches=[r["name"] for r in json.loads(fetch(GH+"branches"))],
              openreview=dict(note=note["id"],title=note["content"]["title"]["value"],
                              attachment=note["content"]["supplementary_material"]["value"],status=status,error=failure),
              model_revision=HF,models=models)
    dump(D/"availability.json",info)
if __name__=="__main__":main()
