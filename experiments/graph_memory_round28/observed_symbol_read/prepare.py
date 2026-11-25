"""Only four pre-change parquet columns may be requested here. No modified-file or region labels."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from urllib.error import HTTPError,URLError
from urllib.parse import quote
from urllib.request import urlopen
import re,time
import pyarrow.parquet as pq
from common28 import *
COLUMNS=["repo","instance_id","base_commit","problem_statement"]
MAIN={"sphinx-doc/sphinx","pytest-dev/pytest","pylint-dev/pylint","mwaskom/seaborn","django/django"}
DJ=re.compile(r"\b(?:format(?:ting|ter)?|date(?:time)?|widget|display|render(?:ing)?|template|verbose_name|plural|translation|localized|localisation)\b",re.I)
RISK=re.compile(r"\b(?:security|insecure|vulnerab\w*|exploits?|attacks?|attacker\w*|injection|malicious|untrusted|cve(?:-\d+)?|unsafe|arbitrary.code|privilege|traversal|remote.code|denial.of.service|overflow|SQL|XSS|crypto\w*|credential\w*|password\w*|auth(?:entica\w*)?|hacking|poisoning|ransomware|weapons?|pathogen\w*|csrf|ddos|ssrf|sandbox|unauthori[sz]ed|race.condition|deserializ\w*|pickle|shell|payload|buffer.overrun|phishing|firearm|military|penetration.testing)\b",re.I)
ROOTS={"huggingface/diffusers":("diffusers",),"huggingface/transformers":("transformers",),"huggingface/trl":("trl",),"huggingface/accelerate":("accelerate",),"keras-team/keras":("keras",),"ukplab/sentence-transformers":("sentence_transformers",),"qiskit/qiskit":("qiskit",),"ds4sd/docling":("docling",),"flet-dev/flet":("flet",),"ultralytics/ultralytics":("ultralytics",),"pydantic/pydantic":("pydantic",),"mlflow/mlflow":("mlflow",),"streamlit/streamlit":("streamlit",),"lightning-ai/pytorch-lightning":("lightning","pytorch_lightning"),"py-pdf/pypdf":("pypdf",),"vllm-project/vllm":("vllm",),"networkx/networkx":("networkx",),"sktime/sktime":("sktime",),"roboflow/supervision":("supervision",),"speechbrain/speechbrain":("speechbrain",),"cupy/cupy":("cupy",),"zarr-developers/zarr-python":("zarr",),"numba/numba":("numba",),"optuna/optuna":("optuna",),"kornia/kornia":("kornia",),"zulko/moviepy":("moviepy",),"albumentations-team/albumentations":("albumentations",)}
def prod(path):
    p=PurePosixPath(path);parts=set(s.casefold() for s in p.parts)
    return (p.suffix==".py" and bool(re.fullmatch(r"[\w/.\-]+",path)) and not p.is_absolute() and ".." not in parts and not parts.intersection({"tests","testing","test","doc","docs","examples","benchmarks","scripts","security","auth","crypto","cryptography","sessions","gis"}) and not p.name.startswith("test_") and not p.name.endswith("_test.py") and not RISK.search(path.replace("_"," ").replace("/"," ")))
def mentioned(text,repo):
    valid=[]
    for m in re.finditer(r"(?:[A-Za-z0-9._\-]+[\\/])+[A-Za-z0-9_\-]+\.py\b",text):
        parts=m[0].replace("\\","/").split("/")
        for i,name in enumerate(parts):
            if name not in ROOTS[repo.lower()]:continue
            cand="/".join(parts[i:])
            for v in ([("src/"+cand),cand,("lib/"+cand)] if i and parts[i-1]=="src" else [cand,"src/"+cand,"lib/"+cand]):
                if prod(v) and v not in valid:valid.append(v)
    return valid[:8]
def download(args):
    r,q,paths=args;attempts=[]
    for path in paths:
        key=digest("\0".join((r["repo"],r["base_commit"],path)));f=P/"files"/key
        url="https://raw.githubusercontent.com/"+r["repo"]+"/"+r["base_commit"]+"/"+quote(path)
        err=None
        for i in range(3):
            try:
                if not f.exists():
                    with urlopen(url,timeout=15) as h:b=h.read(3*1024*1024+1)
                    if len(b)>3*1024*1024:raise ValueError("over3MiB")
                    f.write_bytes(b)
                attempts.append([path,"ok"]);break
            except HTTPError as ex:
                err="http_"+str(ex.code)
                if ex.code<500:break
            except (OSError,ValueError) as ex:err=type(ex).__name__
            if i<2:time.sleep(1+i)
        if f.exists():
            return dict(issue=q,repo=r["repo"],commit=r["base_commit"],path=path,file=key,sha=sha(f),bytes=f.stat().st_size),attempts
        attempts.append([path,err])
    return None,attempts
def main(panel):
    checks();(P/"files").mkdir(parents=True,exist_ok=True)
    verified=panel=="swe";meta=pq.read_table(V if verified else B,columns=COLUMNS).to_pylist()
    source={x["instance_id"]:x for x in map(json.loads,S.open(encoding="utf8")) if x["dataset"]=="verified"} if verified else {}
    counts=Counter();todo=[];queries={};selection={}
    for r in meta:
        q=r["instance_id"];repo=r["repo"].lower();text=r["problem_statement"];counts["all"]+=1
        if repo not in (MAIN if verified else ROOTS):continue
        counts["allowed_repo"]+=1
        if RISK.search(text) or (repo=="django/django" and not DJ.search(text)):counts["excluded_domain"]+=1;continue
        if verified:
            if q not in source:counts["no_explore"]+=1;continue
            series=defaultdict(list)
            for p,records in source[q]["read_step_info"].items():
                for x in records:series[x["traj_path"]].append((x["step_idx"],p))
            if not series:counts["no_trace"]+=1;continue
            traj=min(series,key=lambda s:digest(q+"\0"+s))
            valid=sorted([(step,digest(q+"\0"+p),p) for step,p in series[traj] if prod(p)])
            if not valid:counts["no_production_open"]+=1;continue
            step,_,first=valid[0];paths=[first]
            selection[q]={"trajectory":traj,"step":step}
        else:paths=mentioned(text,r["repo"])
        if not paths:counts["no_explicit_path"]+=1;continue
        assert re.fullmatch(r"[a-f0-9]{40}",r["base_commit"])
        todo.append((r,q,paths));queries[q]=text
    out=[];attempts={}
    with ThreadPoolExecutor(6) as pool:
        for (_,q,_),(row,log) in zip(todo,pool.map(download,todo),strict=True):
            attempts[q]=log
            if row is None:counts["unavailable_file"]+=1;continue
            if verified:row.update(selection[q])
            out.append(row)
    counts["selected"]=len(out)
    save(P/(panel+"-queries.json"),{r["issue"]:queries[r["issue"]] for r in out});save(D/(panel+"-inputs.json.gz"),out)
    save(D/(panel+"-dataset.json"),dict(counts=counts,repositories=Counter(x["repo"] for x in out),attempts=attempts,queries=sha(P/(panel+"-queries.json")),inputs=sha(D/(panel+"-inputs.json.gz")),protocol=sha(D/"PROTOCOL_RU.md"),code=sha(D/"prepare.py"),parquet_columns=COLUMNS))
    print(panel,counts,Counter(x["repo"] for x in out))
if __name__=="__main__":
    import sys
    main(sys.argv[1])

