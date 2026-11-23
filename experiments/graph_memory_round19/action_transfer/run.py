"""Reproduce sealed choices and handle failed collection separately from actual test-call failures."""
from concurrent.futures import ThreadPoolExecutor
import sys
import subprocess
import tempfile
import platform
from pathlib import Path
import numpy as np
import study as st
from core import *

def execute(base,old,new,chosen,memory):
    for f,digest in get("forecast-lock.json").items():assert h((D/f).read_bytes())==digest
    def clean_module(pair):
        module,record=pair;reply=st.issue(base,new,old,"new","clean","target-clean-"+module,record["paths"],timeout=100)
        assert "error" not in reply and not reply["collection_errors"],(module,reply)
        return module,reply["status"]
    with ThreadPoolExecutor(max_workers=4) as pool:clean=dict(pool.map(clean_module,memory.items()))
    put("clean-target.json.gz",clean)
    def per_site(entry):
        sid,pred=entry;m=pred["module"];tag=h(sid.encode())[:15];calls={}
        choices=[pred[k] for k in ("pairs","reach","line","lexical","last")]+pred["placebo"]
        for j,tid in enumerate(sorted(set(choices)-{None})):
            raw=st.issue(base,new,old,"new","mutant","isolated-"+tag+"-"+str(j),[tid],sid,timeout=12)
            if tid in raw["status"]:status=raw["status"][tid]
            elif raw.get("error")=="timeout":status="timeout"
            elif raw.get("collection_errors"):status="collection_error"
            else:raise RuntimeError((sid,tid,raw))
            calls[tid]=dict(old_passed=True,target_clean=clean[m].get(tid),target_changed=status,detected=(status=="failed" and clean[m].get(tid)=="passed"))
        raw=st.issue(base,new,old,"new","mutant","matrix-"+tag,memory[m]["paths"],sid,timeout=24)
        error=raw.get("error") or ("collection_error" if raw.get("collection_errors") else None)
        mat={"code":raw["code"],"error":error,"tests":{k:v for k,v in raw["status"].items() if k in memory[m]["tests"]}}
        return sid,calls,mat
    acts={};matrix={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for j,(sid,a,m) in enumerate(pool.map(per_site,chosen.items()),1):
            acts[sid]=a;matrix[sid]=m
            if j%8==0:print("executed",j,"/",len(chosen),flush=True)
    put("execution-receipts.json.gz",acts);put("exhaustive-matrix.json.gz",matrix)
    return clean,acts,matrix
def run(mode):
    with tempfile.TemporaryDirectory(prefix="runtime-",dir=D,ignore_cleanup_errors=True) as tmp:
        base=Path(tmp);old,a=st.fetch(OLD,base);new,b=st.fetch(NEW,base)
        put("source-lock.json",[a,b]);target,desc=sites(old,new);put("roster.json",dict(sites=target,counts=desc))
        put("design-lock.json",{p:h((D/p).read_bytes()) for p in ("PROTOCOL_RU.md","source-lock.json","roster.json","study.py","worker.py","core.py")})
        if mode=="all":
            mem=st.acquisition(base,old,new);forecasts=st.plan(target,mem)
        else:mem=get("memory.json.gz");forecasts=get("forecasts.json.gz")
        put("execution-lock.json",{f:h((D/f).read_bytes()) for f in ("run.py","forecast-lock.json","EXECUTION_NOTE_RU.md")})
        clean,acts,matrix=execute(base,old,new,forecasts,mem)
        st.summarize(forecasts,acts,matrix,clean)
        native=subprocess.check_output([st.TEST_PYTHON,"-B","-c","import platform,pytest;print(platform.python_version(), pytest.__version__)"],text=True).strip()
        put("environment.json",{"analysis_python":sys.version.split()[0],"test_python_and_pytest":native,"numpy":np.__version__,"platform":platform.platform(),"workers":4})
if __name__=="__main__":run(sys.argv[1])
