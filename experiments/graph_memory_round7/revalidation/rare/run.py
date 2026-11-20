"""Evaluate unchanged scope guards on a prespecified earlier set of wheel histories."""
import argparse, importlib.util, json, sys
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from packaging.version import Version,InvalidVersion
HERE=Path(__file__).resolve().parent
UP=HERE.parent
sys.path.insert(0,str(UP))
from fetch import fetch,download
from common import modules,digest
from predict import rows_for
from score import oracle
spec=importlib.util.spec_from_file_location("binding_run",UP/"binding/run.py")
binding=importlib.util.module_from_spec(spec);spec.loader.exec_module(binding)
basefiles=[UP/"sources.json",UP/"binding/sources.json"]
def save(p,data):
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
def pin():
    src={}
    for file in basefiles:
        for row in json.loads(file.read_bytes()):
            v=Version(row["version"])
            if row["project"] not in src or v<src[row["project"]]:src[row["project"]]=v
    def select(item):
        proj,cap=item; url=f"https://pypi.org/pypi/{proj}/json"
        results=[]
        for ver,rs in json.loads(fetch(url))["releases"].items():
            try:v=Version(ver)
            except InvalidVersion:continue
            if v>=cap or v.is_prerelease or v.is_devrelease or v.is_postrelease or v.local:continue
            viable=sorted((r for r in rs if r["filename"].endswith("-none-any.whl") and not r["yanked"] and r["upload_time_iso_8601"]<"2025-01-01"),key=lambda r:r["filename"])
            if not viable:continue
            r=viable[0]
            results.append((v,dict(project=proj,version=ver,name=r["filename"],url=r["url"],uploaded=r["upload_time_iso_8601"],sha256=r["digests"]["sha256"],source=url)))
        return [r for _,r in sorted(results,key=lambda pair:pair[0])[-16:]]
    path=HERE/"sources.json"
    if not path.exists():
        with ThreadPoolExecutor(6) as ex:rows=[r for group in ex.map(select,src.items()) for r in group]
        save(path,rows)
    rows=json.loads(path.read_bytes())
    with ThreadPoolExecutor(6) as ex:list(ex.map(download,rows))
    print("wheels:",len(rows),flush=True)
def predict():
    with (HERE/"decisions.jsonl").open("w",encoding="utf8",newline="\n") as out:
        for panel,file in [("transfer_strong_control",basefiles[1]),("earlier",HERE/"sources.json")]:
            groups=defaultdict(list)
            for row in json.loads(file.read_bytes()):groups[row["project"]].append(row)
            for proj,items in groups.items():
                before=modules(items[0]["name"])
                for old,new in zip(items,items[1:]):
                    after=modules(new["name"])
                    full={(r["path"],r["caller"]):r["reuse"]["dependencies"] for r in rows_for(proj,old,new,before,after,Counter())}
                    checked=0
                    for path,raw in sorted(before.items()):
                        if raw==after.get(path):continue
                        try:
                            for r in binding.observations(raw,after.get(path)):
                                checked+=1
                                m=r["reuse"];m["full"]=full[path,r["caller"]]
                                out.write(json.dumps(dict(panel=panel,project=proj,old=old["version"],new=new["version"],path=path,caller=r["caller"],old_answer=r["old_answer"],reuse=m),separators=(",",":"))+"\n")
                        except (UnicodeError,SyntaxError,ValueError):continue
                    assert checked==len(full),(proj,checked,len(full))
                    before=after
                print(panel,proj,flush=True)
    deps=[HERE/"PROTOCOL.md",HERE/"run.py",HERE/"sources.json",HERE/"decisions.jsonl",*basefiles,UP/"binding/run.py",UP/"score.py",UP/"common.py",UP/"predict.py"]
    import os
    save(HERE/"prediction-lock.json",{Path(os.path.relpath(p,HERE)).as_posix():digest(p.read_bytes()) for p in deps})
def score():
    for f,h in json.loads((HERE/"prediction-lock.json").read_bytes()).items():assert digest((HERE/f).read_bytes())==h
    sources={(r["project"],r["version"]):r["name"] for m in [basefiles[1],HERE/"sources.json"] for r in json.loads(m.read_bytes())}
    totals=defaultdict(lambda:defaultdict(Counter));byproject=defaultdict(lambda:defaultdict(Counter))
    opens=defaultdict(set);last=None;deltas=[];n=Counter()
    with (HERE/"outcomes.jsonl").open("w",encoding="utf8",newline="\n") as out:
        for ln in (HERE/"decisions.jsonl").read_text("utf8").splitlines():
            r=json.loads(ln);panel=r["panel"];k=(r["project"],r["new"]);path=r["path"]
            if last!=k: last=k;data=modules(sources[k]);parsed={}
            if path not in parsed:parsed[path]=oracle(data.get(path))[0]
            truth=parsed[path].get(r["caller"])==r["old_answer"];n[panel]+=1
            for arm,reuse in r["reuse"].items():
                totals[panel][arm][("correct_reuse" if truth else "stale") if reuse else "reread"]+=1
                if not reuse:opens[panel,arm].add((*k,path))
            if r["reuse"]["positive"] and not r["reuse"]["selective"]:
                byproject[panel][k[0]]["false_alarm" if truth else "stale_prevented"]+=1
                deltas.append(dict(panel=panel,project=k[0],old=r["old"],new=k[1],path=path,caller=r["caller"],stale_prevented=not truth))
            out.write(json.dumps([panel,*k,path,r["caller"],truth],separators=(",",":"))+"\n")
    for panel,arms in totals.items():
        for arm,d in arms.items():d["distinct_files_to_open"]=len(opens[panel,arm])
    save(HERE/"results.json",dict(n=n,totals=totals,selective_disagreements=byproject,examples=deltas))
    print(json.dumps(dict(n=n,totals=totals,selective_disagreements=byproject),indent=1))
if __name__=="__main__":{"fetch":pin,"predict":predict,"score":score}[sys.argv[1]]()
