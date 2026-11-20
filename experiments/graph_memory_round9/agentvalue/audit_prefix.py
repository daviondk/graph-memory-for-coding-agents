"""Run only visible nodeids in separate native pytest processes; compare full dynamic traces."""
import concurrent.futures
import os
import runpy
import subprocess
import sys
from pathlib import Path
import run as r

def one(n):
    p=r.ts(n);pre=r.get(p/"preflight.json")
    base=p/"base"/"checkout";out=p/"prefix_only_native_order";out.mkdir(exist_ok=True)
    args=[str(r.ENV),str(Path(__file__).resolve()),"child",str(base),n,str(out),*[k for k in r.names(r.fn(r.Q/"python_testcases","test_"+n).read_text("utf8")) if k in pre["early"]]]
    process=subprocess.run(args,cwd=base,capture_output=True,timeout=30,env={**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"})
    (out/"pytest.log").write_bytes(process.stdout+process.stderr)
    x=r.get(out/"trace.json.gz")["records"];old=r.get(p/"prefix.json.gz");assert set(x)==set(old)
    return {"id":n,"identical_outcomes":all(x[k]["status"]==old[k]["status"] for k in x),
            "identical_line_sequence":all(x[k]["lines"]==old[k]["lines"] for k in x),
            "identical_edges":all(x[k]["edges"]==old[k]["edges"] for k in x),
            "num_cases":len(x),"rank_line_same":r.rank(x,"lines")==r.rank(old,"lines"),"rank_edge_same":r.rank(x,"edges")==r.rank(old,"edges")}

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="child":
        import pytest
        _,_,root,n,out,*ids=sys.argv
        native=pytest.main
        def run_selected(args,**kwargs):
            return native([args[0]+"::"+name for name in ids]+args[1:],**kwargs)
        pytest.main=run_selected
        sys.argv=[str(r.D/"worker.py"),root,n,out]
        runpy.run_path(str(r.D/"worker.py"),run_name="__main__")
    else:
        with concurrent.futures.ThreadPoolExecutor(3) as ex:rows=list(ex.map(one,r.answers()))
        result={"tasks":len(rows),"prefix_cases":sum(x["num_cases"] for x in rows),"all_rankings_equal":all(x["rank_line_same"] and x["rank_edge_same"] for x in rows),"rows":rows}
        r.dump(r.D/"prefix_verification.json",result);print(result)
