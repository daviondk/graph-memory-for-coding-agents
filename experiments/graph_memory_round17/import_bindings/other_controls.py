"""Uninstrumented import-aware alternatives on clean actual Git clones."""
import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from cli_check import study
from experiment import ROOT, sha, save

POLICIES = ["filemon","mortadelo"]


def cli(exe,cwd,flag,report_path):
    command=[str(exe),"-B","-m","pytest","-q","-o","addopts=","--junitxml="+str(report_path)]
    if flag:
        command.append("--"+flag)
    command.extend(study.FILES)
    env = {k:v for k,v in os.environ.items() if k not in ("PYTHONPATH","PYTEST_ADDOPTS","PYTEST_DISABLE_PLUGIN_AUTOLOAD")}
    start=time.perf_counter()
    res=subprocess.run(command,cwd=cwd,env={**env,"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1"},capture_output=True,timeout=90)
    assert res.returncode in (0,1,5) and report_path.is_file(), (res.stdout+res.stderr).decode()[-1500:]
    xml=report_path.read_bytes()
    cases={e.attrib["classname"]+"::"+e.attrib["name"]:("fail" if e.find("failure") is not None or e.find("error") is not None else "pass")
           for e in ET.fromstring(xml).iter("testcase")}
    return dict(cases=cases,seconds=time.perf_counter()-start,rc=res.returncode,xml=xml.decode(),
                stdout=res.stdout.decode(),stderr=res.stderr.decode())


def main():
    base=Path("D:/CodexResearch/x20-r17-import-binding-runs")/("controls-"+sha(Path(__file__).read_bytes())[:16])
    base.mkdir(exist_ok=False)
    panels={}
    for policy in POLICIES:
        exe=Path("D:/CodexResearch/x20-binding-"+policy+"/Scripts/python.exe")
        version=subprocess.check_output([str(exe),"-c",f"from importlib.metadata import version;print(version('pytest-{policy}'))"]).decode().strip()
        panel={}
        for kind,(old,new) in study.MUTATIONS.items():
            sink=base/(policy+"_"+kind)
            sink.mkdir()
            project=sink/"repo"
            subprocess.run(["git","-c","core.autocrlf=false","clone","--quiet","--shared",str(study.UPSTREAM),str(project)],check=True)
            probe=subprocess.check_output([str(exe),"-B","-c","import colorama.ansi;print(colorama.ansi.__file__)"],cwd=project).decode().strip()
            assert Path(probe).resolve()==project/study.MODULE
            pre=cli(exe,project,policy,sink/"warm.xml")
            stable=cli(exe,project,policy,sink/"stable.xml")
            assert len(pre["cases"])==26 and all(v=="pass" for v in pre["cases"].values())
            target=project/study.MODULE
            content=study.source(study.MODULE)
            assert target.read_bytes()==content and content.count(old.encode())==1
            stamp=target.stat().st_mtime+15
            target.write_bytes(content.replace(old.encode(),new.encode()))
            os.utime(target,(stamp,stamp))
            chosen=cli(exe,project,policy,sink/"selected.xml")
            oracle=cli(exe,project,None,sink/"all.xml")
            assert set(oracle["cases"])==set(pre["cases"])
            fail={k for k,v in oracle["cases"].items() if v=="fail"}
            panel[kind]=dict(version=version,unchanged=stable,pre=pre,selected=chosen,oracle=oracle,
                             failed=sorted(fail),missed=sorted(fail-set(chosen["cases"])))
        panels[policy]=panel
        save("other-controls.gz",panels)
    summary={p:{k:dict(unchanged=len(v["unchanged"]["cases"]),rerun=len(v["selected"]["cases"]),
                       failures=len(v["failed"]),missed=len(v["missed"])) for k,v in panel.items()} for p,panel in panels.items()}
    save("other-controls.json",summary)
    print(summary)


if __name__=="__main__":
    main()

