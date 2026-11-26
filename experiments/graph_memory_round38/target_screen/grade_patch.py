"""Score an independently frozen production patch on the eight published PyBaMM test IDs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import patch

D = Path(__file__).resolve().parent
TARGET = "pybamm-team__pybamm-4267"
STATE = D / "evaluator"
CASE = D / "specs" / TARGET
VENDOR = Path(os.environ.get("VIBE_CHECKOUT", "D:/CodexResearch/x20-official-vibe/VibeMemBench")) / "scripts/vendor"
sys.path.insert(0, str(VENDOR))
from log_parsers import parse_log_pytest

def digest(data):
    return hashlib.sha256(data).hexdigest()

def child(args, cwd, env, timeout=120):
    result = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    return result.returncode, result.stdout.decode("utf8", errors="replace")

def checked(args, cwd, env):
    code, output = child(args, cwd, env)
    if code: raise ValueError(output[-2000:])
    return output

def extract_source(archive, work):
    spec = next(x for x in json.loads((D/"screen.json").read_bytes())["selected"] if x["instance"] == TARGET)
    if digest(archive.read_bytes()) != spec["archive"]["sha256"]:
        raise ValueError("wrong source archive")
    files = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile(): continue
            relative = PurePosixPath(*PurePosixPath(member.name).parts[1:])
            destination = (work / relative).resolve()
            if not destination.is_relative_to(work) or destination == work or ".git" in relative.parts:
                raise ValueError("invalid source path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(tar.extractfile(member).read())
            files += 1
    if files != spec["archive"]["file_count"]: raise ValueError("unexpected source tree")

def ordinary(diff, work, env):
    if not diff.read_bytes().strip(): return []
    if diff.stat().st_size > 200_000: raise ValueError("patch over 200 kB")
    flat = diff.read_text(encoding="utf8").splitlines()
    forbidden = ("old mode ", "new mode ", "new file mode ", "deleted file mode ", "GIT binary patch", "Binary files ", "rename from ", "rename to ", "copy from ", "copy to ")
    if any(line.startswith(forbidden) for line in flat): raise ValueError("requires edits to existing regular files")
    paths = []
    for record in checked(["git","apply","--numstat","-z",str(diff)],work,env).split("\0"):
        if not record: continue
        fields = record.split("\t")
        if len(fields)!=3 or not fields[0].isdigit() or not fields[1].isdigit(): raise ValueError("non-text patch")
        rel=PurePosixPath(fields[2])
        if rel.parts[:1]!=("pybamm",) or any(p.startswith(".") or "\\" in p or ":" in p for p in rel.parts) or rel.suffix!=".py" or not (work/rel).is_file():
            raise ValueError("expected existing Python package source")
        paths.append(rel.as_posix())
    if not paths or len(set(paths)) != len(paths): raise ValueError("expected ordinary unified diff")
    checked(["git","apply","--check",str(diff)],work,env)
    return paths

def official_result(case, candidate, exitcode, output, scratch):
    local = importlib.util.spec_from_file_location("vibe_official_eval", VENDOR/"eval.py")
    ev = importlib.util.module_from_spec(local)
    local.loader.exec_module(ev)
    # Upstream requires a nonempty patch even when replaying an already computed baseline log.
    spec = dict(case, patch=candidate.decode() if candidate.strip() else "\n", test_patch=(CASE/"test_patch.diff").read_text(encoding="utf8"))
    with patch.object(ev, "LOGS_DIR", scratch/"upstream_logs"), patch.object(ev,"run_in_container",return_value=(exitcode,output)):
        out = ev.evaluate_instance(spec, "captured-windows-log", None)
    return dict(passed_match=out["passed_match"],passed_actual=out["passed_actual"],passed_expected=out["passed_expected"])

def grade(diff, out, py, archive, paper_extras):
    case = json.loads((CASE/"case.json").read_bytes())
    f,p=set(case["FAIL_TO_PASS"]),set(case["PASS_TO_PASS"])
    assert (len(f), len(p),len(f&p))==(1,7,0)
    out = out.resolve()
    log,xmlout=out.with_suffix(".log"),out.with_suffix(".xml")
    if len({out,log,xmlout})!=3 or out.suffix!=".json" or any(x.exists() for x in (out,log,xmlout)):raise ValueError("use a new .json output path")
    out.parent.mkdir(parents=True,exist_ok=True)
    data=diff.read_bytes() if diff else b""
    temp_root=Path(os.environ.get("PYBAMM_GRADE_TMP","D:/CodexResearch/x20-r38-pybamm-grade-temp")).resolve()
    temp_root.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if k.upper() in {"PATH","PATHEXT","SYSTEMROOT","SYSTEMDRIVE","WINDIR","COMSPEC","PROCESSOR_ARCHITECTURE","USERPROFILE"}}
    with tempfile.TemporaryDirectory(prefix="p-",dir=temp_root) as td:
        scratch=Path(td).resolve(); work=scratch/"repository"; work.mkdir()
        env.update(TEMP=str(scratch), TMP=str(scratch), PYTHONHASHSEED="0", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",PYTEST_ADDOPTS="-n0",PYTHONPATH=str(work))
        if paper_extras:
            overlay=(STATE/"jax-supplement").resolve()
            if not overlay.is_dir():raise FileNotFoundError(overlay)
            env["PYTHONPATH"]=os.pathsep.join((str(work),str(overlay)))
            del env["PYTEST_ADDOPTS"]
            env["PYTEST_XDIST_AUTO_NUM_WORKERS"]="1"
            env["JAX_PLATFORMS"]="cpu"
        extract_source(archive,work)
        checked(["git","init","-q"],work,env)
        payload=scratch/"candidate.diff";payload.write_bytes(data)
        touched=ordinary(payload,work,env)
        if touched: checked(["git","apply",str(payload)],work,env)
        checked(["git","apply","--check",str(CASE/"test_patch.diff")],work,env)
        checked(["git","apply",str(CASE/"test_patch.diff")],work,env)
        active=checked([str(py),"-B","-c","from pathlib import Path; import pybamm; print(Path(pybamm.__file__).resolve())"],work,env)
        package=(work/"pybamm/__init__.py").resolve()
        if not any(line.strip().casefold()==str(package).casefold() for line in active.splitlines()):raise RuntimeError("local checkout is not being imported")
        args=case["install_config"]["test_cmd"].split()
        if args[0]!="pytest" or args[-1]!="tests/unit/test_util.py":raise RuntimeError("unexpected test command")
        xml=scratch/"report.xml"
        code,text=child([str(py),"-B","-m","pytest","--junitxml",str(xml),*args[1:]],work,env,180)
        if not xml.is_file(): raise RuntimeError("pytest did not produce JUnit output")
        log.write_bytes(text.encode());xmlout.write_bytes(xml.read_bytes())
        native=parse_log_pytest(text)
        independent={}
        for node in ET.parse(xml).iter("testcase"):
            name=args[-1]+"::"+node.attrib["classname"].rsplit(".",1)[-1]+"::"+node.attrib["name"]
            independent[name]=next((s for k,s in (("failure","FAILED"),("error","ERROR"),("skipped","SKIPPED")) if node.find(k) is not None),"PASSED")
        ids=f|p;complete=all(k in native and native[k]==independent.get(k) for k in ids)
        passed={k for k,s in native.items() if s=="PASSED"}
        literal=official_result(case,data,code,text,scratch)
        result=dict(instance=TARGET,patch_sha256=digest(data),base_commit=case["base_commit"],production_files=touched,source_archive_sha256=digest(archive.read_bytes()),evaluator_sha256=digest(Path(__file__).read_bytes()),official_test_patch_sha256=digest((CASE/"test_patch.diff").read_bytes()),
            backend="Windows CPU, private temporary source tree, pytest single worker",published_image=False,paper_optional_packages=paper_extras,
            package_import_in_private_checkout=True,exit_code=code,official_parser_sha256=digest((VENDOR/"log_parsers.py").read_bytes()),official_exact_scorer_sha256=digest((VENDOR/"eval.py").read_bytes()),
            complete_observation=complete,fail_to_pass=[len(f&passed),len(f)],pass_to_pass=[len(p&passed),len(p)],
            registered_success=bool(complete and ids<=passed),official_exact_passed_match=literal["passed_match"],
            unexpected_passed=sorted(passed-ids),junit_only_outside_registered=sorted(set(independent)-ids),native_statuses=native,junit_statuses=independent,
            log_sha256=digest(log.read_bytes()),junit_sha256=digest(xmlout.read_bytes()))
    out.write_bytes((json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode())
    print(json.dumps({k:result[k] for k in ("complete_observation","fail_to_pass","pass_to_pass","registered_success","official_exact_passed_match","patch_sha256")}))
    return 0 if complete else 2

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    group=cli.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline",action="store_true")
    group.add_argument("--patch",type=Path)
    cli.add_argument("--out",type=Path,required=True)
    cli.add_argument("--python",type=Path,default=STATE/"venv/Scripts/python.exe")
    cli.add_argument("--archive",type=Path,default=STATE/"archive"/(TARGET+".tar.gz"))
    cli.add_argument("--paper-extras",action="store_true",help="load separately installed CPU JAX and citation dependencies from the published package extras")
    args=cli.parse_args()
    sys.exit(grade(args.patch,args.out,args.python.resolve(),args.archive.resolve(),args.paper_extras))

