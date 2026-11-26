"""Run the released pytest target in two private CPU source trees; no agent or trace commands."""
from inputs import COMMIT,D,R,V,row,sha,save
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,os,platform,subprocess,sys,time,xml.etree.ElementTree as ET
VENDOR=V/"scripts/vendor";sys.path.insert(0,str(VENDOR))
from log_parsers import parse_log_pytest
TARGET="traitlets/config/tests/test_loader.py"
ARGS=["--no-header","-rA","--tb=line","--color=no","-p","no:cacheprovider","-W","ignore::DeprecationWarning",TARGET]
def run(args,location,env,**kw):
    return subprocess.run(args,cwd=location,env=env,capture_output=True,text=True,encoding="utf8",errors="replace",timeout=80,**kw)
def xmldata(p):
    out={}
    for node in ET.parse(p).iter("testcase"):
        name=node.attrib["classname"].rsplit(".",1)[-1]+"::"+node.attrib["name"]
        out[TARGET+"::"+name]="FAILED" if node.find("failure") is not None else ("SKIPPED" if node.find("skipped") is not None else ("ERROR" if node.find("error") is not None else "PASSED"))
    return out
def main():
    x=row();assert " ".join(["pytest",*ARGS])==x["install_config"]["test_cmd"];testsrc=R/"test_patch.diff";prod=R/"patch.diff"
    py=R/"venv/Scripts/python.exe"
    env={k:v for k,v in os.environ.items() if k.upper() in ("PATH","SYSTEMROOT","COMSPEC","PATHEXT","WINDIR","USERPROFILE","SYSTEMDRIVE","NUMBER_OF_PROCESSORS")}
    temp=R/"test-temp";temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp),TMP=str(temp),PYTHONNOUSERSITE="1",PYTHONDONTWRITEBYTECODE="1",PYTHONUTF8="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    f2p=set(x["FAIL_TO_PASS"]);p2p=set(x["PASS_TO_PASS"]);assert len(f2p)==2 and len(p2p)==60 and not f2p&p2p
    logs=D/"logs";logs.mkdir(exist_ok=True);result={}
    for arm in ("original","base","reference"):
        p=R/("base" if arm=="original" else arm)
        if arm=="original":
            source_before={k:sha(p/k) for k in ("traitlets/traitlets.py",TARGET)}
        if arm!="original":
            run(["git","init","--quiet","."],p,env,check=True)
            assert Path(run(["git","rev-parse","--show-toplevel"],p,env,check=True).stdout.strip()).resolve()==p.resolve()
            for patch in ([prod,testsrc] if arm=="reference" else [testsrc]):
                a=run(["git","apply","--check","--whitespace=nowarn",str(patch)],p,env)
                assert a.returncode==0,a.stderr
                run(["git","apply","--whitespace=nowarn",str(patch)],p,env,check=True)
        src={k:sha(p/k) for k in ("traitlets/traitlets.py",TARGET)}
        actual=run([str(py),"-c","from pathlib import Path; import traitlets; print(Path(traitlets.__file__).resolve())"],p,env,check=True)
        assert Path(actual.stdout.strip()).resolve().is_relative_to(p.resolve())
        begin=time.perf_counter()
        a=run([str(py),"-B","-m","pytest",*ARGS],p,env)
        text=a.stdout+a.stderr
        (logs/(arm+".txt")).write_text(text.replace(str(R),"<runtime>"),encoding="utf8")
        parsed=parse_log_pytest(text)
        xml=R/(arm+".xml")
        b=run([str(py),"-B","-m","pytest",*ARGS[:-1],"--junitxml",str(xml),TARGET],p,env)
        assert b.returncode==a.returncode and parsed==xmldata(xml),(a.returncode,b.returncode,parsed,xmldata(xml))
        passed={k for k,s in parsed.items() if s=="PASSED"}
        result[arm]=dict(exit=a.returncode,f2p=[sum(k in passed for k in f2p),len(f2p)],
          p2p=[sum(k in passed for k in p2p),len(p2p)],statuses=Counter(parsed.values()),
          missing_expected=sorted((f2p|p2p)-set(parsed)),extra=sorted(set(parsed)-(f2p|p2p)),
          exact_pass_set=passed==f2p|p2p,parsed=parsed,source_sha=src,base_source_sha=source_before,
          native_log=sha(logs/(arm+".txt")),junit_matches=True,
          observed_seconds_two_passes=round(time.perf_counter()-begin,3))
    assert result["base"]["source_sha"][TARGET]==result["reference"]["source_sha"][TARGET]
    assert result["base"]["source_sha"]["traitlets/traitlets.py"]==source_before["traitlets/traitlets.py"]
    assert result["reference"]["source_sha"]["traitlets/traitlets.py"]!=source_before["traitlets/traitlets.py"]
    save(D/"results.json",dict(arms=result,agent_episodes=0,solver_calls=0,environment=platform.platform(),
                              python=run([str(py),"--version"],D,env).stdout.strip(),backend="Windows isolated venv",
                              selection="calibration only",phase="historical reference patch plus released test patch",
                              native_parser_sha=sha(VENDOR/"log_parsers.py")))
    for arm,r in result.items():print(arm,r["exit"],r["f2p"],r["p2p"],r["statuses"],r["missing_expected"],r["extra"])
if __name__=="__main__":main()
