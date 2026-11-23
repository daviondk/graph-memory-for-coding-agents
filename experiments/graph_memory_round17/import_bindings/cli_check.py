"""Recheck the Colorama comparison with stock, uninstrumented pytest/Testmon commands."""
import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec

from experiment import ROOT, PY, save, sha

loader=SourceFileLoader("color_research",str(ROOT/"colorama.py.experiment"))
spec=spec_from_loader(loader.name,loader)
study=module_from_spec(spec)
loader.exec_module(study)
ENVIRONMENTS = {"2.3.0":PY,"2.3.1":Path("D:/CodexResearch/x20-binding-testmon-current/Scripts/python.exe")}


def native(executable, cwd, name, testmon):
    xml=cwd/(name+"-junit.xml")
    args=[str(executable),"-B","-m","pytest","-q","-o","addopts=","--junitxml="+str(xml)]
    if testmon:
        args.append("--testmon")
    args.extend(study.FILES)
    env={k:v for k,v in os.environ.items() if k not in ("PYTEST_DISABLE_PLUGIN_AUTOLOAD","PYTEST_ADDOPTS","PYTHONPATH")}
    env.update(PYTHONDONTWRITEBYTECODE="1",PYTHONUTF8="1")
    t=time.perf_counter()
    res=subprocess.run(args,cwd=cwd,capture_output=True,env=env,timeout=90)
    assert res.returncode in (0,1,5) and xml.is_file(), (res.stdout+res.stderr).decode()[-700:]
    content=xml.read_bytes()
    root=ET.fromstring(content)
    cases={r.get("classname")+"::"+r.get("name"):("failed" if r.find("failure") is not None or r.find("error") is not None
             else "skipped" if r.find("skipped") is not None else "passed") for r in root.iter("testcase")}
    return dict(cases=cases,rc=res.returncode,seconds=time.perf_counter()-t,xml=content.decode(),
                stdout=res.stdout.decode(errors="replace"),stderr=res.stderr.decode(errors="replace"))


def main():
    root=Path("D:/CodexResearch/x20-r17-import-binding-runs")/("cli-"+sha(Path(__file__).read_bytes())[:16])
    root.mkdir(exist_ok=False)
    source=study.source(study.MODULE)
    rows={}
    for version,exe in ENVIRONMENTS.items():
        version_actual=subprocess.check_output([str(exe),"-c","from importlib.metadata import version; print(version('pytest-testmon'),version('pytest'),version('coverage'))"]).decode().strip()
        assert version_actual.split()[:2]==[version,"8.4.2"]
        panel={}
        for kind,(before,after) in study.MUTATIONS.items():
            cwd=root/version/kind
            study.checkout(cwd)
            check=subprocess.check_output([str(exe),"-B","-c","import colorama.ansi;print(colorama.ansi.__file__)"],cwd=cwd).decode().strip()
            assert Path(check).resolve()==cwd/study.MODULE
            pre=native(exe,cwd,"warm",True)
            no_change=native(exe,cwd,"stable",True)
            assert len(pre["cases"])==26 and set(pre["cases"].values())=={"passed"} and not no_change["cases"]
            p=cwd/study.MODULE
            stamp=p.stat().st_mtime+15
            altered=source.replace(before.encode(),after.encode())
            p.write_bytes(altered)
            os.utime(p,(stamp,stamp))
            after_edit=native(exe,cwd,"changed",True)
            oracle=native(exe,cwd,"full",False)
            assert oracle["cases"].keys()==pre["cases"].keys()
            fail={k for k,v in oracle["cases"].items() if v=="failed"}
            panel[kind]=dict(warm=pre,stable=no_change,changed=after_edit,full=oracle,missed=sorted(fail-after_edit["cases"].keys()),
                             imported=check,mtime_after=p.stat().st_mtime,changed_sha=sha(altered))
        rows[version]=dict(versions=version_actual,cases=panel)
        save("cli-checks.gz",rows)
    summary={v:{c:dict(selected=len(g["changed"]["cases"]),failed=sum(s=="failed" for s in g["full"]["cases"].values()),
                        missed=len(g["missed"])) for c,g in d["cases"].items()} for v,d in rows.items()}
    save("cli-results.json",summary)
    print(summary)


if __name__=="__main__":
    main()

