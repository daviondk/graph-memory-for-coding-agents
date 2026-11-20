"""Score committed public predictions. Never imported by the prediction process."""
from collections import Counter
import difflib
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import subprocess
import tarfile
import tempfile

import duckdb

D=Path(__file__).resolve().parent
WORK=D.parents[1]
OLD=WORK/"graph_memory_round6/repair/transfer"
DB=Path("D:/CodexResearch/x20-round4-verified.parquet")
ARMS=("bm25","doclink","shuffled","r6_flat")

def sha(x):
    return hashlib.sha256(x).hexdigest()
def read(p):
    return json.loads(p.read_bytes())
def save(p,obj):
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n","utf8")

def external_sites(task,patch):
    paths={s for s in re.findall(r"(?m)^(?:--- a/|\+\+\+ b/)([^\s]+)",patch)}
    allowed={s for s in paths if s.startswith("sphinx/") and s.endswith(".py") and not {"tests","testing","benchmarks"}&set(s.split("/")) and not Path(s).name.startswith("test_")}
    assert all(".." not in s.split("/") and "\\" not in s for s in allowed)
    if not allowed:return set(),len(paths)
    before={}
    with tarfile.open(D/"inputs"/task/"base.tar.gz") as tf:
        for member in tf:
            p=member.name.partition("/")[2]
            if member.isfile() and p in allowed:before[p]=tf.extractfile(member).read()
    applied=set()
    with tempfile.TemporaryDirectory(dir=D) as temp:
        root=Path(temp)
        for path,data in before.items():
            fp=root/path;fp.parent.mkdir(exist_ok=True,parents=True);fp.write_bytes(data)
        subprocess.run(["git","init","--quiet"],cwd=root,check=True,capture_output=True)
        proc=subprocess.run(["git","apply","--whitespace=nowarn",*["--include="+p for p in sorted(allowed)],"-"],cwd=root,input=patch.encode("utf8"),capture_output=True)
        if proc.returncode:raise ValueError((task,proc.stderr[:200]))
        sites=set()
        for path,data in before.items():
            fp=root/path
            if not fp.is_file():continue
            a=data.decode("utf8",errors="replace").splitlines();b=fp.read_bytes().decode("utf8",errors="replace").splitlines()
            for tag,lo,hi,_,_ in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
                if tag!="equal":
                    sites.update((path,n) for n in range(lo+1,max(lo+1,hi)+1));applied.add(path)
    if before and not sites and any((("--- a/"+p+"\n") in patch and ("+++ b/"+p+"\n") in patch) for p in before):
        raise ValueError(("Unexpected no-change patch after isolated apply",task))
    return sites,len(paths-applied)

def mask(spans):
    by={}
    for p,lo,hi in spans:
        by.setdefault(p,set()).update(range(lo,hi+1))
    return by
def intersect(sites,ranges):
    return sum(n in ranges.get(p,()) for p,n in sites)

def paired(rows,a,b):
    ds=[x["arms"][a]["hit"]-x["arms"][b]["hit"] for x in rows]
    w=sum(v>0 for v in ds);l=sum(v<0 for v in ds);n=len(ds)
    rng=random.Random(71027)
    boot=sorted(sum(rng.choices(ds,k=n))/n for _ in range(10000))
    sign=min(1.,2*sum(math.comb(w+l,k) for k in range(min(w,l)+1))/2**(w+l))
    return {"wins":w,"losses":l,"ties":n-w-l,"delta_pp":100*sum(ds)/n,"ci95_pp":[100*boot[249],100*boot[9749]],"mcnemar_exact_p":sign}

def main():
    lock=read(D/"predictions.lock.json")
    assert lock["protocol"]==sha((D/"PROTOCOL_RU.md").read_bytes())
    assert lock["code"]==sha((D/"predict.py").read_bytes())
    for i,h in lock["predictions"].items():assert sha((D/"predictions"/(i+".json.gz")).read_bytes())==h
    sym_sites={r["id"]:set(map(tuple,r["sites"])) for r in read(OLD/"cpu_rows.json")}
    sph=read(D/"cohort_sphinx.json")
    assert sha(DB.read_bytes())==sph["data_sha"]
    db=duckdb.connect()
    raw=db.execute("select instance_id,patch from read_parquet(?) where repo='sphinx-doc/sphinx'",[str(DB)]).fetchall()
    external=dict(raw)
    rows=[]
    for task in lock["predictions"]:
        p=json.loads(gzip.decompress((D/"predictions"/(task+".json.gz")).read_bytes()))
        if task in sym_sites:
            sites=sym_sites[task];panel="sympy-reused";excluded=None
        else:
            assert task in sph["ids"]
            sites,excluded=external_sites(task,external[task]);panel="sphinx-external"
        visible=sum(path in p["paths"] for path,n in sites);possible=intersect(sites,mask(p["available"]))
        row={"id":task,"panel":panel,"target_old_lines":len(sites),"sites":sorted(sites),"excluded_changed_files":excluded,
             "in_files":visible,"in_blocks":possible,"n_files":len(p["paths"]),"n_blocks":len(p["available"]),"arms":{}}
        for arm in ARMS:
            a=p["arms"][arm]
            assert a["tokens"]<=1800
            cover=intersect(sites,mask(a["kept"]))
            row["arms"][arm]={"hit":int(cover>0),"cover":cover,"tokens":a["tokens"],"sha256":sha(a["packet"].encode("utf8"))}
            assert cover<=possible<=visible<=len(sites)
        rows.append(row)
    report={}
    for panel in ("sympy-reused","sphinx-external"):
        rs=[x for x in rows if x["panel"]==panel]
        tot={"n":len(rs),"n_nonempty_gold":sum(bool(x["target_old_lines"]) for x in rs),"n_files_hit":sum(bool(x["in_files"]) for x in rs),"n_blocks_hit":sum(bool(x["in_blocks"]) for x in rs),
        "target_old_lines":sum(x["target_old_lines"] for x in rs),"lines_in_files":sum(x["in_files"] for x in rs),"lines_in_blocks":sum(x["in_blocks"] for x in rs),
        "arms":{},"pairs":{}}
        for arm in ARMS:
            hit=sum(x["arms"][arm]["hit"] for x in rs)
            tot["arms"][arm]={"tasks_hit":hit,"hit_given_block_ceiling":hit/tot["n_blocks_hit"] if tot["n_blocks_hit"] else None,
            "lines_covered":sum(x["arms"][arm]["cover"] for x in rs),"mean_tokens":statistics.mean(x["arms"][arm]["tokens"] for x in rs)}
        for ref in ("bm25","shuffled","r6_flat"):tot["pairs"]["doclink_minus_"+ref]=paired(rs,"doclink",ref)
        report[panel]=tot
    save(D/"scores_per_issue.json",rows)
    save(D/"results.json",report)
    save(D/"evaluation.lock.json",{"predictions_lock_sha256":sha((D/"predictions.lock.json").read_bytes()),"evaluator":sha(Path(__file__).read_bytes()),
    "previous_evaluation":sha((OLD/"cpu_rows.json").read_bytes()),"dataset":sph["data_sha"],"rows":sha((D/"scores_per_issue.json").read_bytes()),"results":sha((D/"results.json").read_bytes())})
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
