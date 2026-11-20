"""Evaluate the held-out native tests alone, in upstream collection order, on all distinct source variants."""
import collections
import concurrent.futures
import os
import subprocess
from pathlib import Path
import run as r
def one(n):
    pre=r.get(r.ts(n)/"preflight.json");orig=r.get(r.ts(n)/"grades.json")
    exp=r.get(r.D/"probes"/"tasks"/n/"grades.json")
    ass=r.get(r.D/"assign.json")[n];p_ass=r.get(r.D/"probes"/"assign.json")[n]
    source=r.fn(r.Q/"python_programs",n).read_text("utf8");gold=r.fn(r.Q/"correct_python_programs",n).read_text("utf8")
    full={m:a["tests"]["states"] for m,a in {**orig,**exp}.items()}
    full.update(base=r.get(r.ts(n)/"base/testdata/outcomes.json")["states"],gold=r.get(r.ts(n)/"gold/testdata/outcomes.json")["states"])
    strings={"base":source,"gold":gold}
    for d,assigned in [(r.D,ass),(r.D/"probes",p_ass)]:
        for m,k in assigned.items():
            proposal=r.get(d/"calls"/(k+".json.gz"))["response"]["choices"][0]["message"]["content"]
            strings[m]=r.patched(source,proposal)
    ids=[k for k in r.names(r.fn(r.Q/"python_testcases","test_"+n).read_text("utf8")) if k in pre["hold"]]
    seen={};byarm={}
    for m,s in strings.items():
        sig=r.key(s)
        if sig not in seen:
            root=r.copyroot(n,"heldout_only/"+sig[:16],s);out=root.parent/"heldout";out.mkdir(exist_ok=True)
            command=[str(r.ENV),str(r.D/"audit_prefix.py"),"child",str(root),n,str(out),*ids]
            proc=subprocess.run(command,cwd=root,capture_output=True,timeout=30,env={**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"})
            (out/"pytest.log").write_bytes(proc.stdout+proc.stderr)
            src=r.get(out/"trace.json.gz")
            assert set(src["records"])==set(src["xml"])==set(ids)
            assert all(src["records"][k]["status"]==src["xml"][k] for k in ids)
            seen[sig]=src["xml"]
        byarm[m]={"states":seen[sig],"equals_full_projection":all(seen[sig][k]==full[m][k] for k in ids)}
    return {"id":n,"n_unique_sources":len(seen),"held_tests":len(ids),"arms":byarm}
if __name__=="__main__":
    with concurrent.futures.ThreadPoolExecutor(3) as ex:rows=list(ex.map(one,r.answers()))
    result={"tasks":len(rows),"distinct_sources":sum(r["n_unique_sources"] for r in rows),"unique_held_test_functions":sum(r["held_tests"] for r in rows),
            "all_projections_match":all(x["equals_full_projection"] for row in rows for x in row["arms"].values()),"rows":rows}
    r.dump(r.D/"heldout_verification.json",result);print({k:v for k,v in result.items() if k!="rows"})
