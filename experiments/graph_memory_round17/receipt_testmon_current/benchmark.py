"""Evaluate stock, uninstrumented pytest-testmon CLIs on both sealed cohorts with native JUnit scoring."""
from concurrent.futures import ThreadPoolExecutor
import collections
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parent;PRIMARY=ROOT.parent/"receipt_invalidation"
sys.path.insert(0,str(PRIMARY))
from rollback import build,source
from testmon_comparison import as_node
COHORT={"main":PRIMARY,"holdout":ROOT.parent/"receipt_holdout"}
ENVS={"2.3.0":Path("D:/CodexResearch/x20-validity-releases/testmon-env/Scripts/python.exe"),"2.3.1":Path("D:/CodexResearch/x20-binding-testmon-current/Scripts/python.exe")}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(file):
    b=file.read_bytes();return json.loads(gzip.decompress(b) if file.suffix==".gz" else b)
def save(file,obj):
    b=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    (ROOT/file).write_bytes(gzip.compress(b,mtime=0) if file.endswith(".gz") else b)
def execute(py,cwd,xml,nodes,tm):
    cmd=[py,"-B","-m","pytest","-q","--tb=short","--junitxml="+str(xml),"-o","addopts="]
    if tm:cmd.extend(["-p","testmon.pytest_testmon","--testmon","--testmon-forceselect"])
    cmd.extend(nodes);env={**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1"}
    env.pop("PYTHONPATH",None)
    start=time.perf_counter();r=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=180);seconds=time.perf_counter()-start
    txt=r.stdout.decode(errors="replace")+"\n"+r.stderr.decode(errors="replace")
    if r.returncode not in (0,1,5) or not xml.is_file():raise RuntimeError(txt[-2200:])
    content=xml.read_bytes();result={}
    for c in ET.fromstring(content).iter("testcase"):
        modules,cls=c.get("classname").rsplit(".",1)
        n=modules.replace(".","/")+".py::"+cls+"::"+c.get("name");assert n not in result
        result[n]="fail" if c.find("failure") is not None or c.find("error") is not None else "skip" if c.find("skipped") is not None else "pass"
    assert result.keys()<=set(nodes)
    return {"outcomes":result,"rc":r.returncode,"seconds":seconds,"db_bytes":sum(p.stat().st_size for p in cwd.glob(".testmondata*")),"log":txt,"xml":content.decode()}
def main():
    cache=Path("D:/CodexResearch/x20-round17-testmon-stock");cache.mkdir(exist_ok=True)
    versions={}
    for v,py in ENVS.items():
        versions[v]=json.loads(subprocess.check_output([py,"-c","import json,platform,importlib.metadata as m; print(json.dumps([platform.python_version(), *[m.version(p) for p in ('pytest','pytest-testmon','coverage')]]))"]))
        assert versions[v][2]==v
    order=[];cohort_sha={}
    for label,folder in COHORT.items():
        r=folder/"rollback-roster.json";cohort_sha[label]=sha(r.read_bytes())
        for b in load(r)["blocks"]:
            for ver in ENVS:order.append((label,b,ver))
    order.sort(key=lambda t:sha((t[0]+t[1]["commit"]+t[2]).encode()))
    save("assignment.json",{"environments":versions,"cohort_sha":cohort_sha,"order":[[x,b["commit"],v] for x,b,v in order],"protocol":sha((ROOT/"PROTOCOL_RU.md").read_bytes()),"code_sha":sha((ROOT/"benchmark.py").read_bytes())})
    check=load(ROOT/"assignment.json")
    first=load(ROOT/"original-assignment.json")
    assert all(check[k]==first[k] for k in ("order","environments","cohort_sha","protocol"))
    stamp=sha((ROOT/"assignment.json").read_bytes())
    retained=cache/("completed-"+stamp[:20])
    retained.mkdir(exist_ok=True)
    def one(package):
        num,(label,b,v)=package
        target=retained/(label+"-"+b["commit"]+"-"+v+".gz")
        if target.exists():
            record=load(target)
            assert (record["cohort"],record["commit"],record["version"])==(label,b["commit"],v)
            return record
        with tempfile.TemporaryDirectory(dir=cache) as t:
            t=Path(t);cwd=t/"tree";build(b,cwd)
            nodes=[as_node(x["name"]) for x in b["tests"]]
            warm=execute(ENVS[v],cwd,t/"warm.xml",nodes,True);assert set(warm["outcomes"])==set(nodes)
            unchanged=execute(ENVS[v],cwd,t/"same.xml",nodes,True)
            original=(cwd/b["module"]).read_bytes();assert sha(original)==b["after_sha"]
            new=source(b["parent"],b["module"]);assert sha(new)==b["before_sha"]
            (cwd/b["module"]).write_bytes(new)
            selected=execute(ENVS[v],cwd,t/"selected.xml",nodes,True)
            full=execute(ENVS[v],cwd,t/"all.xml",nodes,False);assert set(full["outcomes"])==set(nodes)
            assert all(o==full["outcomes"][n] for n,o in selected["outcomes"].items())
            record={"cohort":label,"commit":b["commit"],"version":v,"warm":warm,"unchanged":unchanged,"selected":selected,"full":full}
            print(num+1,len(order),label,v,b["commit"][:8],flush=True)
            partial=target.with_suffix(".part")
            partial.write_bytes(gzip.compress(json.dumps(record,sort_keys=True).encode(),mtime=0))
            partial.replace(target)
            return record
    with ThreadPoolExecutor(max_workers=3) as pool:
        recs=list(pool.map(one,enumerate(order)))
    save("official-runs.gz",recs)
    summary={};pairs=[]
    for label,folder in COHORT.items():
        graph={p["commit"]:set() for p in load(folder/"testmon-graph-forecasts.gz")}
        for r in load(folder/"testmon-graph-forecasts.gz"):
            if r["graph_recheck"]:graph[r["commit"]].add(r["node"])
        summary[label]={}
        previous={r["commit"]:set() for r in load(folder/"testmon-graded.gz")}
        for r in load(folder/"testmon-graded.gz"):
            if r["testmon_recheck"]:previous[r["commit"]].add(r["node"])
        for version in ENVS:
            count=collections.Counter();times=collections.Counter()
            for row in recs:
                if (row["cohort"],row["version"])!=(label,version):continue
                c=row["commit"];pos={n for n,o in row["warm"]["outcomes"].items() if o=="pass"};sel=set(row["selected"]["outcomes"])&pos
                fails={n for n,o in row["full"]["outcomes"].items() if o=="fail" and n in pos}
                count.update({"num_commits":1,"positive":len(pos),"fail":len(fails),"graph":len(graph[c]),"graph_false_pass":len(fails-graph[c]),"testmon":len(sel),"testmon_false_pass":len(fails-sel),"all_selected_including_nonpass":len(row["selected"]["outcomes"]),"unmodified_positive_selected":len(pos&row["unchanged"]["outcomes"].keys()),"n_differ_from_instrumented_230":len(sel.symmetric_difference(previous[c]))})
                for name in ("warm","unchanged","selected","full"):times[name]+=row[name]["seconds"]
                pairs.append({"cohort":label,"version":version,"commit":c,"positive":len(pos),"testmon":len(sel),"graph":len(graph[c]),"fails":len(fails),"testmon_false_pass":len(fails-sel),"graph_false_pass":len(fails-graph[c])})
            summary[label][version]={"count":count,"seconds":times}
    save("results.json",{"panels":summary,"pairs":pairs})
    print(summary)
if __name__=="__main__":main()
