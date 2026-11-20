"""Verify every chosen old-cache update by running the selected test on its current snapshot."""
import concurrent.futures
import gzip
import math
import os
import shutil
import subprocess
import tempfile
import time
from experiment import ROOT,WORK,R9,read,save,digest,check
from pathlib import Path
ENV=Path("D:/CodexResearch/x20-round9-test311-runtime/venv/Scripts/python.exe")
TMP=Path("D:/CodexResearch/x20-round10-agenttest-runtime").resolve()
TMP.mkdir(exist_ok=True)
def apply(path,patch):
    subprocess.run(["git","apply","--whitespace=nowarn","-"],input=patch.encode(),cwd=path,
        env={**os.environ,"GIT_CEILING_DIRECTORIES":str(path.parent)},capture_output=True,check=True)
def test_job(args):
    task,cohort,both=args
    origin=(WORK/("graph_memory_round8/agent" if cohort=="testmemory_compat" else "graph_memory_round7/reader")/"tasks"/task)
    cfg=read(origin/"grading.json");records=[]
    with tempfile.TemporaryDirectory(prefix="validate-",dir=TMP) as tmp:
        path=Path(tmp).resolve()/"repo";assert path.is_relative_to(TMP)
        shutil.copytree(origin/"base",path,ignore=shutil.ignore_patterns("__pycache__",".git",".pytest_cache"))
        apply(path,cfg["test_patch"])
        for d in ("revert","fix"):
            if d=="fix":apply(path,cfg["patch"])
            for node in sorted(both[d]):
                filename=digest((task+d+node).encode())[:16]+".log"
                env={**os.environ,"PYTHONPATH":str(path),"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"}
                t=time.monotonic()
                with (ROOT/"tests"/filename).open("wb") as f:
                    p=subprocess.run([str(ENV),"-B","-m","pytest","-q","-o","addopts=","--disable-warnings","--tb=line",node],
                        cwd=path,env=env,timeout=120,stdout=f,stderr=subprocess.STDOUT)
                content=(ROOT/"tests"/filename).read_bytes()
                status=("passed" if p.returncode==0 and b"1 passed" in content else "failed" if p.returncode==1 and b"1 failed" in content else "unresolved")
                records.append(dict(task=task,direction=d,node=node,observed=status,wall=time.monotonic()-t,log=filename,sha256=digest(content)))
    return records
def main():
    check("sealed.json");check("oracle-sealed.json")
    (ROOT/"tests").mkdir(exist_ok=True)
    answers=read(ROOT/"answers.json")+read(ROOT/"oracle-answers.json")
    inputs={r["id"]:r for r in read(ROOT/"inputs.json")}
    for r in inputs.values():
        for arm,index in (("baseline",r["baseline"]),("baseline_graph",r["baseline_graph"])):
            answers.append(dict(id=r["id"],arm=arm,index=index))
    todo={};logs=[]
    for a in answers:
        r=inputs[a["id"]];node=r["nodes"][a["index"]] if a["index"] is not None else None
        todo.setdefault((r["task"],r["cohort"]),dict(fix=set(),revert=set()))
        if node:todo[r["task"],r["cohort"]][r["direction"]].add(node)
    jobs=[(*key,both) for key,both in todo.items()]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        for chunk in ex.map(test_job,jobs):logs.extend(chunk)
    save(ROOT/"executed.json",logs)
    actual={(v["task"],v["direction"],v["node"]):v["observed"] for v in logs}
    refs={}
    for panel in {r["cohort"] for r in inputs.values()}:
        for x in read(R9/panel/"outcomes.json"):
            refs[x["task"],x["direction"],x["node"]]=x
    rows=[]
    for a in answers:
        r=inputs[a["id"]]
        k=(r["task"],r["direction"])
        node=r["nodes"][a["index"]] if a["index"] is not None else None
        status=actual.get((*k,node))
        flips=sum(refs[(*k,n)]["changed"] for n in r["nodes"])
        picked=refs.get((*k,node),{})
        correct=status==picked.get("actual") if node else None
        gain=bool(node and correct and status!=r["prior"][a["index"]])
        rows.append(dict(task=r["task"],cohort=r["cohort"],direction=r["direction"],arm=a["arm"],node=node,
             selected_index=a["index"],prior=picked.get("prior"),full_run=picked.get("actual"),isolated=status,
             status_matches_full=correct,found_change=gain,stale_left=flips-int(gain),total_changes=flips,
             prompt=a.get("usage",{}).get("prompt_tokens",0),generated=a.get("usage",{}).get("completion_tokens",0)))
    save(ROOT/"rows.json",rows)
    result={}
    for d in ("fix","revert"):
        subset=[r for r in rows if r["direction"]==d]
        meta={}
        for arm in sorted({r["arm"] for r in subset}):
            g=[r for r in subset if r["arm"]==arm]
            meta[arm]=dict(n=len(g),changed_found=sum(x["found_change"] for x in g),stale_left=sum(x["stale_left"] for x in g),
                invalid=sum(x["node"] is None for x in g),prompt=sum(x["prompt"] for x in g),generated=sum(x["generated"] for x in g))
        pairs={}
        for base in ("shuffled","off","baseline_graph"):
            graph={r["task"]:r["found_change"] for r in subset if r["arm"]=="graph"}
            ctrl={r["task"]:r["found_change"] for r in subset if r["arm"]==base}
            changes=[int(v)-int(ctrl[k]) for k,v in graph.items()]
            w,l=changes.count(1),changes.count(-1);n=w+l
            p=min(1,2*sum(math.comb(n,i) for i in range(min(w,l)+1))/2**n) if n else 1
            pairs[base]=dict(wins=w,losses=l,ties=len(changes)-n,mcnemar_p=p)
        result[d]=dict(arms=meta,graph_against=pairs,available_changes=sum(r["total_changes"] for r in subset if r["arm"]=="graph"))
    result["verification"]=dict(unique_actual_reruns=len(logs),isolated_mismatches=[r for r in rows if r["status_matches_full"] is False],
           unique_gpu_requests=len({r["call"] for r in answers if "call" in r}))
    save(ROOT/"results.json",result)
    print(result)
if __name__=="__main__":main()
