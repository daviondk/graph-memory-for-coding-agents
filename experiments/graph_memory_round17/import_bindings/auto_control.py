"""Generate blinded code snapshots, freeze predictions, and audit native pytest executions against the original panel."""
import gzip
import json
import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from cli_check import study
from experiment import ROOT, PY, positive, sha, save
from auto_predict import forecast


def native(cwd, output, ids, observer=False):
    junit = output.with_suffix(".xml")
    cmd = [str(PY),"-B"]
    cmd += [str(ROOT/"auto_observer.py")] if observer else ["-m","pytest"]
    cmd += ["-q","-o","addopts=","--junitxml="+str(junit),*ids]
    env = dict(os.environ,PYTHONPATH=str(cwd),PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",PYTHONDONTWRITEBYTECODE="1",
               PYTHONUTF8="1",AUTO_CHANGED_FILE=study.MODULE,AUTO_OBSERVATIONS=str(output))
    begin=time.perf_counter()
    proc=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=60)
    log=proc.stdout.decode(errors="replace")+"\n"+proc.stderr.decode(errors="replace")
    if proc.returncode not in (0,1) or not junit.is_file():raise RuntimeError(log[-1600:])
    xml=junit.read_text(encoding="utf8")
    found={}
    for case in ET.fromstring(xml).iter("testcase"):
        mod,cls=case.get("classname").rsplit(".",1)
        node=mod.replace(".","/")+".py::"+cls+"::"+case.get("name")
        assert node not in found
        found[node]="fail" if any(c.tag in ("failure","error") for c in case) else "skip" if case.find("skipped") is not None else "pass"
    return {"nodes":found,"xml":xml,"rc":proc.returncode,"seconds":time.perf_counter()-begin,"log":log}


def main():
    frozen=json.loads((ROOT/"colorama-lock.json").read_bytes())
    for name,h in frozen["files"].items():assert sha((ROOT/name).read_bytes())==h
    for path,h in frozen["inputs"].items():assert sha(study.source(path))==h
    original=study.source(study.MODULE)
    versions={};labels={}
    for label,(left,right) in study.MUTATIONS.items():
        assert original.count(left.encode())==1
        data=original.replace(left.encode(),right.encode())
        anon=sha(data)
        assert anon not in versions
        versions[anon]=data;labels[anon]=label
    first={"files":{n:sha((ROOT/n).read_bytes()) for n in ("AUTOMATIC_PROTOCOL_RU.md","auto_observer.py","auto_predict.py","auto_control.py","colorama-lock.json")},
           "commit":study.COMMIT,"before_sha":sha(original),"variant_sha":sorted(versions)}
    save("auto-input-lock.json",first)
    prior_plan=json.loads((ROOT/"colorama-plan.json").read_bytes())
    previous=json.loads(gzip.decompress((ROOT/"colorama-runs.gz").read_bytes()))
    with tempfile.TemporaryDirectory(dir="D:/CodexResearch/x20-r17-import-binding-runs") as s:
        scratch=Path(s);warm_dir=scratch/"initial";study.checkout(warm_dir)
        warm=native(warm_dir,scratch/"observed.json",study.FILES,True)
        receipt=json.loads((scratch/"observed.json").read_bytes())
        assert set(warm["nodes"])==set(receipt["tests"]) and all(s=="pass" for s in warm["nodes"].values()) and len(warm["nodes"])==26
        assert all(positive(v) for v in receipt["outcomes"].values())
        save("auto-warm.gz",{"native":warm,"receipt":receipt})
        predictions={oid:forecast(original,versions[oid],receipt) for oid in sorted(versions)}
        save("auto-forecasts.json",predictions)
        save("auto-forecast-seal.json",{n:sha((ROOT/n).read_bytes()) for n in ("auto-input-lock.json","auto-warm.gz","auto-forecasts.json")})
        records={};summary={}
        for oid,plan in predictions.items():
            label=labels[oid];old=previous[label];assert old["changed_digest"]==oid
            directory=scratch/oid;study.checkout(directory);(directory/study.MODULE).write_bytes(versions[oid])
            full=native(directory,scratch/(oid+"-all.json"),study.FILES)
            assert full["nodes"].keys()==warm["nodes"].keys()
            failed={n for n,v in full["nodes"].items() if v=="fail"}
            assert failed==set(old["failed"])
            chosen=plan["nodeids"];ref=set(prior_plan[label]["bindings"])
            execution=native(directory,scratch/(oid+"-selected.json"),chosen) if chosen else None
            actual=execution["nodes"] if execution else {}
            assert set(actual)==set(chosen) and all(full["nodes"][k]==v for k,v in actual.items())
            records[oid]={"label":label,"full":full,"selected":execution}
            summary[label]={"changed_sha":oid,"sources":plan["changes"],"fallback":plan["full_fallback"],"original_selected":len(ref),
                "actual_selected":len(actual),"added":sorted(set(chosen)-ref),"removed":sorted(ref-set(chosen)),"full_failures":len(failed),
                "caught":len(failed&set(actual)),"false_reuse":sorted(failed-set(actual))}
        save("auto-runs.gz",records)
        save("auto-results.json",{"cases":summary,"public_and_private_names_except_dunder":receipt["exports"],"project":study.MODULE,
                                 "observed_tests":len(warm["nodes"]),"executed_graph":sum(k["actual_selected"] for k in summary.values())})
        print([(k,v["full_failures"],v["actual_selected"],v["caught"],len(v["added"]),len(v["removed"])) for k,v in summary.items()])
if __name__=="__main__":main()
