"""Grade a frozen ordinary source diff in an ephemeral networkless Linux container."""
import argparse, base64, hashlib, json, re, shlex, shutil, subprocess, sys, tempfile
from pathlib import Path
from inputs import D, R, V, KEY, row, save, sha
from replay import ARGS
sys.path.insert(0,str(V/"scripts/vendor"))
from log_parsers import parse_log_pytest
IMAGE="x20-traitlets-reference:r38"
def screen_diff(data):
    if not data.strip():return
    if len(data)>2_000_000:raise ValueError("patch exceeds 2 MB")
    lines=data.decode("utf-8").splitlines()
    if any(s.startswith(("GIT binary patch","Binary files ","rename from ","rename to ","copy from ","copy to ","new file mode 120000","old mode ","new mode ")) for s in lines):raise ValueError("expected regular text file changes")
    files=[]
    for s in lines:
        if not s.startswith(("diff --git ","--- ","+++ ")):continue
        if s.startswith("diff --git "):
            tokens=shlex.split(s)[2:]
        else:
            tokens=[s[4:].split("\t")[0]]
        for token in tokens:
            if token=="/dev/null":continue
            if token[:2] not in ("a/","b/"):raise ValueError("use standard Git diff a/ and b/ paths")
            p=Path(token[2:])
            if not p.parts or p.is_absolute() or ".." in p.parts or any(a.startswith(".") for a in p.parts):raise ValueError("non-source path")
            if "tests" in p.parts or "test" in p.parts or p.name=="conftest.py" or p.name.startswith("test_"):raise ValueError("submit production diff only, keep candidate tests in a separate artifact")
            files.append(token[2:])
    if not files:raise ValueError("expected unified git source patch")
def grade(patch,out):
    data=patch.read_bytes() if patch else b""
    screen_diff(data)
    spec=row()
    assert " ".join(["pytest",*ARGS])==spec["install_config"]["test_cmd"]
    with tempfile.TemporaryDirectory(dir=R,prefix="grade-") as temp:
        folder=Path(temp)
        (folder/"candidate.diff").write_bytes(data)
        (folder/"assess.diff").write_bytes(spec["test_patch"].encode())
        script="""set -eu
mkdir /tmp/in
python -B -c 'import base64,json,pathlib,sys; d=json.load(sys.stdin); [(pathlib.Path("/tmp/in")/k).write_bytes(base64.b64decode(d[k])) for k in ("candidate.diff","assess.diff")]'
cp -R /traitlets /tmp/work
cd /tmp/work
export HOME=/tmp PYTHONPATH=/tmp/work
git config --global --add safe.directory /tmp/work
if [ -s /tmp/in/candidate.diff ]; then
    git apply --check --whitespace=nowarn /tmp/in/candidate.diff
    git apply --whitespace=nowarn /tmp/in/candidate.diff
fi
git apply --whitespace=nowarn /tmp/in/assess.diff
python -B -c 'import pathlib,traitlets; assert pathlib.Path(traitlets.__file__).resolve().is_relative_to(pathlib.Path("/tmp/work"))'
exec python -B -m pytest """+" ".join(shlex.quote(x) for x in ARGS)
        cp=subprocess.run(["docker","run","-i","--pull=never","--rm","--network","none","--cap-drop","ALL",
                        "--security-opt","no-new-privileges","--user","65534:65534","--read-only","--pids-limit","160",
                        "--memory","512m","--cpus","2","--tmpfs","/tmp:rw,exec,size=96m",
                        IMAGE,"/bin/sh","-c",script],
                        input=json.dumps({q.name:base64.b64encode(q.read_bytes()).decode("ascii") for q in folder.iterdir()}).encode("ascii"),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
        text=cp.stdout.decode("utf-8","replace")
    out.parent.mkdir(parents=True,exist_ok=True); log=out.with_suffix(".log");log.write_text(text,encoding="utf8")
    parsed=parse_log_pytest(text)
    f=set(spec["FAIL_TO_PASS"]);p=set(spec["PASS_TO_PASS"]);passed={k for k,s in parsed.items() if s=="PASSED"}
    result=dict(instance=KEY,patch_sha256=hashlib.sha256(data).hexdigest(),published_image=False,
            image_id=subprocess.check_output(["docker","image","inspect",IMAGE,"--format","{{.Id}}"],text=True).strip(),
            exit_code=cp.returncode,passed_match=passed==p|f,complete_observation=set(parsed)==p|f,
            fail_to_pass=[len(f&passed),len(f)],pass_to_pass=[len(p&passed),len(p)],
            parsed_statuses=parsed,log_sha256=sha(log))
    save(out,result)
    print(json.dumps({k:result[k] for k in ("exit_code","passed_match","complete_observation","fail_to_pass","pass_to_pass","patch_sha256")}))
    return 0 if result["complete_observation"] else 2
if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group(required=True);g.add_argument("--patch",type=Path);g.add_argument("--baseline",action="store_true")
    ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    sys.exit(grade(a.patch,a.out))
