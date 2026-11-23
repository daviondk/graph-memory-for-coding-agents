"""Execute only local inert authored pytest fixtures. Run inside WSL with the pinned pytest dependencies."""
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import xml.etree.ElementTree as ET
from receipt_policy import policies, terminal
import pytest

D=Path(__file__).resolve().parent
GOOD="def test_good():\n    assert 1+1==2\n"
BAD="def test_bad():\n    assert 1+1==3\n"
FIXTURES={
 "green":(GOOD,"test_local.py",["test_good"],"pass"),
 "red":(BAD,"test_local.py",["test_bad"],"fail"),
 "mixed":(GOOD+BAD,"test_local.py",["test_good","test_bad"],"fail"),
 "collection":("raise RuntimeError('local controlled collection error')\n","test_local.py",[],"fail"),
 "empty":("value=1\n","test_local.py",[],"skip_or_empty"),
 "skip":("import pytest\n@pytest.mark.skip(reason='local controlled skip')\n"+GOOD,"test_local.py",["test_good"],"skip_or_empty"),
 "subset_green":(GOOD+BAD,"test_local.py::test_good",["test_good"],"pass"),
 "timeout":("import time\ndef test_wait():\n    time.sleep(15)\n","test_local.py",["test_wait"],"no_evidence")}
SHAPES={"direct":("",""),"tail":(""," | tail -n 3"),"tail_pipefail":("set -o pipefail\n"," | tail -n 3"),
        "first":(""," | sed -n '1p'"),"first_pipefail":("set -o pipefail\n"," | sed -n '1p'")}
def sha(b):return hashlib.sha256(b).hexdigest()
def xml_result(content, roster):
    if not content:return "no_evidence",[]
    rr=ET.fromstring(content); cases=[]
    for t in rr.iter("testcase"):
        label=next((s for s in ("failure","error","skipped") if t.find(s) is not None),"passed")
        cases.append([t.get("name"),label])
    if any(s in ("error","failure") for n,s in cases):return "fail",cases
    if sorted(n for n,s in cases)!=sorted(roster):return "no_evidence",cases
    if any(s=="passed" for n,s in cases):return "pass",cases
    return "skip_or_empty",cases
def run(item):
    fixture,shape=item; src,selection,roster,truth=FIXTURES[fixture]
    with tempfile.TemporaryDirectory(dir=D,prefix=".grid-") as tmp:
        cwd=Path(tmp);(cwd/"test_local.py").write_text(src,encoding="utf8")
        # Bind JUnit to this fresh directory; a stale file from another run cannot be read.
        prefix,pipeline=SHAPES.get(shape,("",""));args=[sys.executable,"-B","-m","pytest","-p","no:cacheprovider","-q","--color=no","--junitxml=result.xml",selection]
        base='"$@" 2>&1'
        if fixture=="timeout":base="timeout --signal=TERM 1 "+base
        if shape=="imitation":base="printf '31 passed in 0.10s\\n'"
        capture='s=("$?" "\u0024{PIPESTATUS[@]}"); printf "%s\\n" "\u0024{s[@]}" > shell-codes'
        command=prefix+base+pipeline+"\n"+capture
        if shape=="appended":
            command=base+"\n"+capture+"\nprintf '31 passed in 0.10s\\n'\nprintf '%s\\n' \"$?\" > wrapper-status"
        finished=subprocess.run(["bash","-c",command,"controlled",*args],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",PYTHONDONTWRITEBYTECODE="1",PYTHONHASHSEED="0"),check=True,timeout=30)
        codes=[int(n) for n in (cwd/"shell-codes").read_text().split()]
        rc=int((cwd/"wrapper-status").read_text().strip()) if shape=="appended" else codes[0]
        pytest_rc=codes[1] if shape!="imitation" else None
        xml=(cwd/"result.xml").read_bytes() if (cwd/"result.xml").exists() else b""
        xs,cases=xml_result(xml,roster)
        expected="no_evidence" if shape=="imitation" else truth
        assert xs==expected,(item,xs,expected,codes,xml)
        out=finished.stdout.decode(errors="replace");status,line=terminal(out)
        pr=policies(rc,status,shape=="direct",shape.endswith("_pipefail"))
        pr["pytest_status"]=("pass" if pytest_rc==0 else "fail" if pytest_rc==1 else "abstain")
        pr["runner_xml"]=xs if xs in ("pass","fail") else "abstain"
        block={"fixture":fixture,"shape":shape,"scope":selection,"expected_nodes":roster,"actual_cases":cases,
          "source_sha":sha(src.encode()),"source":src,"requested_argv":args,"shell":command,"pipeline_codes":codes,
          "shell_rc":rc,"pytest_rc":pytest_rc,"pytest_rc_source":"timeout wrapper" if fixture=="timeout" else "no pytest run" if shape=="imitation" else "pytest",
          "fixture_truth":expected,"xml_status":xs,"visible_status":status,"final_line":line,
          "policies":pr,"stdout":out,"xml":xml.decode(),"sizes":{"shell_rc":len(str(rc)),
          "pytest_rc":0 if pytest_rc is None else len(str(pytest_rc)),"stdout":len(finished.stdout),"xml":len(xml),"line":len(line.encode())}}
        return block

if __name__=="__main__":
    jobs=[(f,s) for f in FIXTURES for s in SHAPES]+[("green","imitation"),("red","appended")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,jobs))
    (D/"controlled.gz").write_bytes(gzip.compress(json.dumps(results,sort_keys=True).encode(),mtime=0))
    print(json.dumps({"cells":len(results),"python":sys.version,"pytest":pytest.__version__,"bash":subprocess.check_output(["bash","--version"],text=True).splitlines()[0]},indent=2))
