"""Anchor observations to a real checkout for each test, then seal predictions without reading benchmark labels."""
import concurrent.futures
import gzip
import json
import os
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from plan import ROOT,CACHE,PY,git,load,put,sha

def select(pair,file,trace,valid):
    names=("all","module","old_function","outer_function","old_line","outer_line")
    if not valid or pair["force_all"] or file in pair["edited_tests"]:return dict.fromkeys(names,True)
    output=dict.fromkeys(names,False);output["all"]=True
    for path,source in pair["modules"].items():
        d=source["change"];obs=trace[path]
        calls=set(obs["calls"]);lines=set(obs["lines"]);loaded=bool(calls or lines)
        output["module"]|=loaded
        for version,dst in (("old","old"),("new","outer")):
            output[dst+"_function"]|=loaded if d[version+"_fallback"] else bool(calls & set(d[version+"_functions"]))
            output[dst+"_line"]|=loaded if d[version+"_fallback"] else bool(lines & set(d["old_lines"]) or calls & set(d[version+"_insert"]))
    return output

def run_one(task):
    pair,file,base_tar,retained,cache=task
    key=sha((pair["current"]+"|"+file).encode())
    output=retained/(key+".gz")
    if output.exists():
        rec=load(output);assert rec["current"]==pair["current"] and rec["file"]==file
        return rec
    with tempfile.TemporaryDirectory(dir=cache) as scratch:
        scratch=Path(scratch);cwd=scratch/"src";cwd.mkdir()
        with tarfile.open(base_tar,"r:") as tar:tar.extractall(cwd,filter="data")
        assert sha((cwd/file).read_bytes())==pair["test_sha"][file]
        for p,m in pair["modules"].items():assert sha((cwd/p).read_bytes())==m["old_sha"]
        conf=scratch/"cfg.json";out=scratch/"out.json";paths=sorted(pair["modules"])
        put(conf,{"test":file,"paths":paths,"out":str(out)})
        env={**os.environ,"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1"}
        env.pop("PYTHONPATH",None);env.pop("PYTEST_ADDOPTS",None)
        begin=time.perf_counter()
        try:
            pr=subprocess.run([str(PY),"-B",str(ROOT/"worker.py"),str(conf)],cwd=cwd,env=env,timeout=150,capture_output=True)
            log=pr.stdout+b"\n"+pr.stderr
            runtime=load(out) if out.is_file() else None
            process_rc=pr.returncode
        except subprocess.TimeoutExpired as e:
            runtime=None;process_rc="timeout";log=(e.stdout or b"")+b"\n"+(e.stderr or b"")
        sec=time.perf_counter()-begin
        passing=set();failed=set()
        if runtime:
            for node,phase,status in runtime["outcomes"]:
                if phase=="call" and status=="passed":passing.add(node)
                if status=="failed":failed.add(node)
        clean=bool(runtime and process_rc==0 and runtime["pytest_rc"]==0 and passing and not failed)
        policy=select(pair,file,runtime["trace"] if runtime else {},clean)
        result={"current":pair["current"],"true_parent":pair["true_parent"],"file":file,"clean":clean,"process_rc":process_rc,
                "passes":len(passing),"failed_items":len(failed),"wall_s":sec,"runtime":runtime,"log":log.decode(errors="replace"),
                "log_sha":sha(log),"policies":policy}
        temp=output.with_suffix(".part.gz");put(temp,result);os.replace(temp,output)
        return result
def main():
    lock=load(ROOT/"plan-lock.json")
    assert all(sha((ROOT/n).read_bytes())==h for n,h in lock.items())
    plan=load(ROOT/"plan.json");cache=CACHE/"runs";cache.mkdir(exist_ok=True)
    retained=CACHE/("completed-"+sha((ROOT/"plan-lock.json").read_bytes())[:18]);retained.mkdir(exist_ok=True)
    jobs=[]
    for p in plan["cohort"]:
        base=p["true_parent"];tar=CACHE/(base+".tar")
        if not tar.exists():tar.write_bytes(git("archive","--format=tar",base))
        jobs.extend((p,f,tar,retained,cache) for f in p["tests"])
    # Each concurrent process extracts a private baseline tree.
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for n,r in enumerate(pool.map(run_one,jobs),1):
            rows.append(r)
            if n%10==0:print("saved",n,"of",len(jobs),flush=True)
    put(ROOT/"forecasts.gz",rows)
    put(ROOT/"forecast-seal.json",{n:sha((ROOT/n).read_bytes()) for n in ("plan-lock.json","forecasts.gz")})
    print("clean",sum(r["clean"] for r in rows),"of",len(rows))
if __name__=="__main__":main()
