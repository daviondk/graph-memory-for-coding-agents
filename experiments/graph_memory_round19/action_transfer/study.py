"""Fetch fixed Boltons snapshots, precommit retrieval, execute actual upstream tests, and archive receipts."""
import collections
from concurrent.futures import ThreadPoolExecutor
import io
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from statistics import mean

import numpy as np
import pytest
from core import D,OLD,NEW,MODULES,h,key,stable,put,get,sites
TEST_PYTHON=os.environ.get("R19_TEST_PYTHON","D:/CodexResearch/x20-round9-test311-runtime/venv/Scripts/python.exe")

def fetch(rev,base):
    url="https://codeload.github.com/mahmoud/boltons/zip/"+rev
    with urllib.request.urlopen(url,timeout=90) as response:blob=response.read()
    z=zipfile.ZipFile(io.BytesIO(blob));folder=base/rev;folder.mkdir()
    hashes={}
    for entry in z.infolist():
        prefix="boltons-"+rev+"/"
        assert entry.filename.startswith(prefix)
        relative=entry.filename[len(prefix):].rstrip("/")
        if not relative or entry.is_dir() or ".." in Path(relative).parts:continue
        if not (relative.startswith("boltons/") and relative.endswith(".py") or relative.startswith("tests/") and relative.endswith(".py")):continue
        content=z.read(entry);file=folder/relative;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(content);hashes[relative]=h(content)
    return folder,{"revision":rev,"url":url,"archive_sha256":h(blob),"source_files":hashes}
def tokens(s):
    return set(re.findall(r"[a-z0-9]+",re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",s).lower()))-{"test","tests","py","self"}
def jaccard(a,b):return len(a&b)/len(a|b) if a|b else 0
def issue(base,repo,old,version,mode,title,nodes,target=None,timeout=45):
    output=base/(title+".out");cfg=base/(title+".json")
    put(cfg,{"repo":str(repo),"tests":str(old),"version":version,"mode":mode,"nodes":nodes,"output":str(output),"target":target})
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",PYTHONHASHSEED="19",PYTHONIOENCODING="utf-8")
    start=time.perf_counter()
    try:proc=subprocess.run([TEST_PYTHON,"-B",str(D/"worker.py"),str(cfg)],capture_output=True,timeout=timeout,env=env)
    except subprocess.TimeoutExpired:return {"code":"timeout","selected":[],"status":{},"error":"timeout"}
    if proc.returncode or not output.exists():
        return {"code":proc.returncode,"selected":[],"status":{},"error":proc.stderr[-1800:].decode("utf8","replace").replace(str(base),"<runtime>")}
    return get(output)
def acquisition(base,old,new):
    manifests={};newbase={}
    def collect(module):
        paths=["tests/test_"+module+".py"]
        if module=="statsutils":paths.append("tests/test_statsutils_histogram.py")
        paths=[p for p in paths if (old/p).is_file()]
        if not paths:return module,{"paths":[],"tests":[],"history":{},"statuses":{}},None
        runs={}
        for mode in ("clean","history"):
            z=issue(base,old,old,"old",mode,"baseline-"+mode+"-"+module,paths,timeout=100)
            if "error" in z or z["collection_errors"]:raise RuntimeError((module,mode,z))
            runs[mode]=z
        assert runs["clean"]["selected"]==runs["history"]["selected"]
        status={k:{"native":runs["clean"]["status"].get(k),"observed":runs["history"]["status"].get(k)} for k in runs["clean"]["selected"]}
        tests=[k for k,rec in status.items() if rec["native"]==rec["observed"]=="passed"]
        return module,{"paths":paths,"tests":tests,"history":{k:runs["history"]["events"].get(k,{}) for k in tests},"statuses":status},None
    with ThreadPoolExecutor(max_workers=4) as pool:
        for module,data,_ in pool.map(collect,MODULES):manifests[module]=data
    put("memory.json.gz",manifests)
    print("history",sum(len(v["tests"]) for v in manifests.values()),"tests",flush=True)
    return manifests
def plan(sites,memory):
    selected={}
    for site in sites:
        sid=site["id"];old=site["old"];m=memory[old["module"]]
        ids=m["tests"];seen=m["history"]
        flags={i:set(seen[i].get(sid,[])) for i in ids}
        term=tokens(old["function"]+" "+old["expression"]);rank={tid:(jaccard(term,tokens(tid)),position) for position,tid in enumerate(ids)}
        def best(fn):return max(ids,key=fn) if ids else None
        def line(k):return ("line" in flags[k],*rank[k])
        def reach(k):return ("predicate" in flags[k],*line(k))
        def pick(equal):return best(lambda k:(k in equal,*reach(k)))
        real={k for k in ids if "equal" in flags[k]};executed=[k for k in ids if "predicate" in flags[k]]
        assert real<=set(executed)
        placebo=[]
        for seed in range(16):
            order=sorted(executed,key=lambda k:h(f"{sid}|{seed}|{k}".encode()))
            if len(order)>1:swapped={k for k,other in zip(order,order[1:]+order[:1]) if other in real}
            else:swapped=real
            assert len(swapped)==len(real)
            placebo.append(pick(swapped))
        selected[sid]={"module":old["module"],"function":old["function"],"historical_candidates":len(ids),"observed_equal":len(real),
                       "observed_predicate":len(executed),"observed_line":sum("line" in f for f in flags.values()),
                       "pairs":pick(real),"placebo":placebo,"reach":best(reach),"line":best(line),"lexical":best(rank.__getitem__),"last":ids[-1] if ids else None}
    put("forecasts.json.gz",selected)
    put("forecast-lock.json",{p:h((D/p).read_bytes()) for p in ("forecasts.json.gz","memory.json.gz","roster.json","design-lock.json")})
    return selected
def experiments(base,old,new,chosen,memory):
    for f,digest in get("forecast-lock.json").items():assert h((D/f).read_bytes())==digest
    clean={}
    def rerun(item):
        m,record=item
        z=issue(base,new,old,"new","clean","target-clean-"+m,record["paths"],timeout=100)
        if "error" in z or z["collection_errors"]:raise RuntimeError((m,z))
        return m,z["status"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for m,s in pool.map(rerun,memory.items()):clean[m]=s
    put("clean-target.json.gz",clean)
    matrix={};replays={}
    def per_site(item):
        sid,pred=item;module=pred["module"];unique=sorted({x for x in (pred["pairs"],pred["reach"],pred["line"],pred["lexical"],pred["last"],*pred["placebo"]) if x is not None})
        tag=h(sid.encode())[:15]
        # Each actually selected test runs in a fresh interpreter on the mutant; share identical actions across policies.
        actions={}
        for j,tid in enumerate(unique):
            z=issue(base,new,old,"new","mutant",f"action-{tag}-{j}",[tid],target=sid,timeout=12)
            status=z["status"].get(tid,"timeout" if z.get("error")=="timeout" else "infrastructure_error")
            if status=="infrastructure_error":raise RuntimeError((sid,tid,z))
            actions[tid]={"old_passed":True,"target_clean":clean[module].get(tid),"target_changed":status,
                          "detected":clean[module].get(tid)=="passed" and status=="failed"}
        # One additional batched evaluation estimates the attainable ceiling from all old eligible tests.
        z=issue(base,new,old,"new","mutant",f"matrix-{tag}",memory[module]["paths"],target=sid,timeout=24)
        res={"code":z["code"],"error":z.get("error"),"tests":{tid:s for tid,s in z["status"].items() if tid in memory[module]["tests"]}}
        return sid,actions,res
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(sid,a,mat) in enumerate(pool.map(per_site,chosen.items()),1):
            replays[sid]=a;matrix[sid]=mat
            if i%8==0:print("executed",i,"/",len(chosen),flush=True)
    put("execution-receipts.json.gz",replays);put("exhaustive-matrix.json.gz",matrix)
    return clean,replays,matrix
def cluster_ci(rows):
    blocks=collections.defaultdict(list)
    for f,d in rows:blocks[f].append(d)
    totals=np.array([sum(v) for _,v in sorted(blocks.items())]);n=np.array([len(v) for _,v in sorted(blocks.items())]);rng=np.random.default_rng(19)
    x=rng.integers(0,len(n),size=(10000,len(n)))
    return np.quantile(totals[x].sum(1)/n[x].sum(1),[.025,.975]).tolist()
def summarize(chosen,cases,mat,clean):
    rows={}
    for sid,rec in chosen.items():
        actions=cases[sid]
        def measured(t):return int(t is not None and actions[t]["detected"])
        ceiling=any(clean[rec["module"]].get(k)=="passed" and s=="failed" for k,s in mat[sid]["tests"].items())
        for k,v in actions.items():
            if mat[sid].get("error") is None and clean[rec["module"]].get(k)=="passed" and v["target_changed"]!="timeout":
                assert mat[sid]["tests"].get(k)==v["target_changed"],(sid,k)
        rows[sid]={**{name:measured(rec[name]) for name in ("pairs","reach","line","lexical","last")},
                   "placebo":[measured(t) for t in rec["placebo"]],"oracle":ceiling if mat[sid]["error"] is None else None,"function":rec["function"],"module":rec["module"]}
    put("outcomes.json",rows)
    ms={method:sum(r[method] for r in rows.values()) for method in ("pairs","reach","line","lexical","last")}
    ps=[sum(row["placebo"][i] for row in rows.values()) for i in range(16)]
    pairs={}
    for baseline in ("placebo","reach","line","lexical","last"):
        groups=[];wins=losses=0
        for row in rows.values():
            other=mean(row[baseline]) if baseline=="placebo" else row[baseline]
            delta=row["pairs"]-other;groups.append((row["function"],delta))
            wins+=delta>0;losses+=delta<0
        pairs[baseline]={"delta":mean(v for _,v in groups),"cluster_ci95":cluster_ci(groups),"positive_sites":wins,"negative_sites":losses}
    summary={"n":len(rows),"functions":len(set(r["function"] for r in rows.values())),"native_unique_actions":sum(len(a) for a in cases.values()),
             "changed_action_status":dict(collections.Counter(a["target_changed"] for v in cases.values() for a in v.values())),
             "target_clean_status":dict(collections.Counter(a["target_clean"] for v in cases.values() for a in v.values())),
             "full_suite_timeout":sum(r["oracle"] is None for r in rows.values()),"oracle_hits":sum(r["oracle"] is True for r in rows.values()),
             "observed_equal_sites":sum(v["observed_equal"]>0 for v in chosen.values()),"observed_predicate_sites":sum(v["observed_predicate"]>0 for v in chosen.values()),
             "same_as_reach":sum(v["pairs"]==v["reach"] for v in chosen.values()),"counts":ms,"placebo_seed_counts":ps,"paired":pairs}
    put("summary.json",summary);print(summary,flush=True)
def main():
    with tempfile.TemporaryDirectory(prefix="runtime-",dir=D,ignore_cleanup_errors=True) as tmp:
        base=Path(tmp);old,one=fetch(OLD,base);new,two=fetch(NEW,base)
        put("source-lock.json",[one,two]);targets,numbers=sites(old,new);put("roster.json",dict(sites=targets,counts=numbers))
        put("design-lock.json",{p:h((D/p).read_bytes()) for p in ("PROTOCOL_RU.md","source-lock.json","roster.json","study.py","worker.py","core.py")})
        print("roster",len(targets),numbers,flush=True)
        mem=acquisition(base,old,new);forecasts=plan(targets,mem);clean,actions,mat=experiments(base,old,new,forecasts,mem)
        summarize(forecasts,actions,mat,clean)
        native=subprocess.check_output([TEST_PYTHON,"-B","-c","import platform,pytest;print(platform.python_version(), pytest.__version__)"],text=True).strip()
        put("environment.json",{"analysis_python":sys.version.split()[0],"test_python_and_pytest":native,"numpy":np.__version__,"platform":platform.platform(),"workers":4})
if __name__=="__main__":main()
