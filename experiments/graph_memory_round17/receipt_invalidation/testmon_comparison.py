"""Compare official testmon to the event graph with the same pytest runtime and frozen test panel."""
import collections
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from rollback import ROOT,CACHE,build,source,read,put,sha

PY=Path("D:/CodexResearch/x20-validity-releases/testmon-env/Scripts/python.exe")

def as_node(name):
    path,cls,method=name.rsplit(".",2)
    return path.replace(".","/")+".py::"+cls+"::"+method
def call(base,sink,tag,nodes,tm,trace):
    output=sink/(tag+".json");junit=sink/(tag+".xml")
    command=[str(PY),"-B","-m","pytest","-p","trace_plugin","-q","--tb=short","--junitxml="+str(junit),"-o","addopts="]
    if tm:command+=["-p","testmon.pytest_testmon","--testmon","--testmon-forceselect"]
    command+=nodes
    env={**os.environ,"PYTHONPATH":os.pathsep.join([str(ROOT),str(base)]),"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1","R17_REPORT":str(output),"R17_TRACE":"1" if trace else "0"}
    begin=time.perf_counter()
    response=subprocess.run(command,env=env,cwd=base,timeout=120,capture_output=True)
    seconds=time.perf_counter()-begin
    log=response.stdout.decode(errors="replace")+"\n"+response.stderr.decode(errors="replace")
    if response.returncode not in (0,1,5) or not output.is_file() or not junit.is_file():raise RuntimeError(tag+":"+log[-3500:])
    record=json.loads(output.read_bytes())
    if record["status"]!=response.returncode:
        assert not record["rows"] and {record["status"],response.returncode}=={0,5}, (record["status"],response.returncode,log[-200:])
    assert set(record["rows"])<=set(nodes)
    return {"native":record,"seconds":seconds,"returncode":response.returncode,"stdout_stderr":log,"junit":junit.read_text(encoding="utf8"),"db_bytes":sum(p.stat().st_size for p in base.glob(".testmondata*"))}
def outcome(r):
    p=r["phases"]
    if "failed" in p.values():return "fail"
    if "skipped" in p.values():return "skip"
    return "pass" if set(p)=={"setup","call","teardown"} and set(p.values())=={"passed"} else "unknown"
def main():
    roster=read(ROOT/"rollback-roster.json")["blocks"]
    assignments={c["commit"]:[as_node(t["name"]) for t in c["tests"]] for c in roster}
    versions=json.loads(subprocess.check_output([str(PY),"-c","import platform, json, importlib.metadata as m; print(json.dumps([platform.python_version(), *[m.version(p) for p in ('pytest','pytest-testmon','coverage')]]))"]))
    put("testmon-assignment.json",{"versions":versions,"nodes":assignments,"hashes":{n:sha((ROOT/n).read_bytes()) for n in ("TESTMON_PROTOCOL_RU.md","rollback-roster.json","testmon_comparison.py","trace_plugin.py")}})
    data={};forecasts=[];post=[];preserve=[]
    parent_path=CACHE/"testmon"
    parent_path.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent_path) as scratch:
        for block in roster:
            commit=block["commit"];base=Path(scratch)/commit/"work";sink=base.parent/"evidence";sink.mkdir(parents=True)
            build(block,base);nodes=assignments[commit]
            pure=call(base,sink,"reference-child",nodes,False,False)
            warm=call(base,sink,"testmon-warm",nodes,True,True)
            calibration=call(base,sink,"unchanged",nodes,True,False)
            assert set(pure["native"]["rows"])==set(warm["native"]["rows"])==set(nodes) and warm["db_bytes"]>0
            data[commit]={"pure_child":pure,"warm":warm,"unchanged":calibration}
            for node in nodes:
                prv=warm["native"]["rows"][node]
                if outcome(prv)==outcome(pure["native"]["rows"][node])=="pass":
                    deps={fn for p,fn in prv["calls"] if p==block["module"]}
                    forecasts.append({"commit":commit,"node":node,"graph_recheck":bool(deps&set(block["changed"])),"seen":sorted(deps),"changed":block["changed"]})
            preserve.append((block,base,sink,nodes))
        put("testmon-warm.gz",data);put("testmon-graph-forecasts.gz",forecasts)
        put("testmon-forecast-seal.json",{n:sha((ROOT/n).read_bytes()) for n in ("testmon-assignment.json","testmon-warm.gz","testmon-graph-forecasts.gz")})
        before={r["commit"]:r for r in roster}
        for block,base,sink,nodes in preserve:
            c=block["commit"];(base/block["module"]).write_bytes(source(block["parent"],block["module"]))
            assert sha((base/block["module"]).read_bytes())==block["before_sha"]
            selected=call(base,sink,"testmon-after",nodes,True,False)
            replay=[call(base,sink,"all-after-"+str(i),nodes,False,False) for i in range(2)]
            assert all(set(a["native"]["rows"])==set(nodes) for a in replay)
            post.append({"commit":c,"selected":selected,"replay":replay})
    put("testmon-runs.gz",post)
    refs={p["commit"]:p for p in post}
    rows=[]
    for p in forecasts:
        hist=refs[p["commit"]];node=p["node"]
        truth=[outcome(a["native"]["rows"][node]) for a in hist["replay"]]
        check=hist["selected"]["native"]["rows"].get(node)
        rows.append({**p,"testmon_recheck":check is not None,"testmon_outcome":outcome(check) if check else None,"outcomes":truth,"truth":truth[0] if truth[0]==truth[1] else "unstable"})
    put("testmon-graded.gz",rows)
    aggregate={}
    for arm in ("testmon_recheck","graph_recheck"):
        used=[p for p in rows if not p[arm]]
        aggregate[arm]={"rerun":len(rows)-len(used),"reuse":len(used),"use_outcomes":collections.Counter(p["truth"] for p in used),"checked_outcomes":collections.Counter(p["truth"] for p in rows if p[arm])}
    aggregate["phases"]={phase:{"ran":sum(len(r[phase]["native"]["rows"]) for r in data.values()),"wall_seconds":sum(r[phase]["seconds"] for r in data.values()),"db_bytes":sum(r[phase]["db_bytes"] for r in data.values())} for phase in ("pure_child","warm","unchanged")}
    aggregate["cost_changed"]={"testmon":sum(p["selected"]["seconds"] for p in post),"all_rep1":sum(p["replay"][0]["seconds"] for p in post),"all_rep2":sum(p["replay"][1]["seconds"] for p in post)}
    aggregate["versions"]=versions
    aggregate["fingerprints"]={"divergent_full_native":sum(p["testmon_outcome"] is not None and p["testmon_outcome"]!=p["truth"] for p in rows),"divergent_selection":sum(p["testmon_recheck"]!=p["graph_recheck"] for p in rows)}
    put("testmon-results.json",aggregate);print(aggregate)
if __name__=="__main__":main()
