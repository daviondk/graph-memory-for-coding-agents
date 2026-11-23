"""Freeze new revisions, real edits, path-level resource types and the local environment."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import tomllib

ROOT=Path(__file__).resolve().parent
R18=ROOT.parents[1]/"graph_memory_round18/namerts_transfer"
sys.path.insert(0,str(R18))
import plan as old
from forecast import select as old_select
CACHE=ROOT/"_runtime"
def prior():
    history=old.load(R18/"plan.json")
    seen=set(history["old_shas"])
    for p in history["cohort"]+old.load(R18/"supplemental-plan.json"):
        seen|={p["current"],p["true_parent"],p["direct_parent"]}
    return seen,history

def classify(p):
    if p=="pyproject.toml":return "toml"
    if p.startswith("loguru/") and p.endswith(".pyi"):return "stub"
    if p.startswith("tests/") and p.endswith(".py") and not p.endswith("conftest.py") and not re.fullmatch(r"tests/test_[^/]+\.py",p):return "helper"
    return None
def config_projection(b):
    try:
        parsed=tomllib.loads(b.decode("utf8"))
        return ["parsed",parsed.get("tool",{}).get("pytest",{}).get("ini_options",None)]
    except (UnicodeError,ValueError,AttributeError):return ["unknown"]
def indexed(b,p):
    try:return old.git("show",b+":"+p)
    except subprocess.CalledProcessError:return None

def material(row,kind,changes):
    b,c=row["true_parent"],row["current"]
    p={**row,**old.features(b,c)}
    resources={}
    for mode,path in changes:
        typ=classify(path)
        if not typ:continue
        left=indexed(b,path) if mode!="A" else None
        right=indexed(c,path) if mode!="D" else None
        r={"kind":typ,"mode":mode,"before_sha":old.sha(left) if left is not None else None,"after_sha":old.sha(right) if right is not None else None}
        if typ=="toml" and left is not None and right is not None:
            r.update(before_projection=config_projection(left),after_projection=config_projection(right))
        resources[path]=r
    p["resources"]=resources
    p["remaining_force_all"]=[s for s in p["force_all"] if s[1] not in resources]
    pool=sorted(old.testfiles(b)&old.testfiles(c),key=lambda f:old.sha(("r19-file|"+c+"|"+f).encode()))
    p.update(panel=kind,pool=pool,tests=pool[:14],test_sha={f:old.sha(old.git("show",b+":"+f)) for f in pool[:14]})
    return p
def main():
    seen,hist=prior();roster=old.git("show",old.VERSION+":dataset/commit_pairs_loguru.json",where=old.PKG)
    rows=json.loads(roster);order=sorted([r for r in rows if r[3]],key=lambda r:old.sha(("r19-resource|"+r[2]).encode()))
    selected=[];flow=[];calibration=None
    for direct,b,c,_ in order:
        msg=old.git("log","-1","--format=%s",c).decode().strip()
        reason="excluded_topic" if old.BAD.search(msg) else "previous_sha" if seen&{direct,b,c} else None
        if reason=="excluded_topic":flow.append({"current":c,"status":reason});continue
        changes=[line.split("\t",1) for line in old.git("diff","--no-renames","--name-status",b,c).decode().splitlines()]
        changed=[p for _,p in changes if classify(p)]
        if not changed and reason is None:reason="no_target_resource"
        primary=(reason is None and len(selected)<4)
        row=dict(current=c,true_parent=b,direct_parent=direct,subject=msg,rank=old.sha(("r19-resource|"+c).encode()))
        flow.append({**row,"status":reason or "candidate","resource_paths":changed,"selected":primary})
        if primary:selected.append(material(row,"new",changes))
        if c.startswith("280e584e"):calibration=material(row,"calibration",changes)
    assert calibration is not None
    assert all(not seen&{p["true_parent"],p["current"],p["direct_parent"]} for p in selected)
    old.put(ROOT/"plan.json",{"cohort":selected,"calibration":[calibration],"flow":flow,"all_prior":sorted(seen),
       "roster_sha":old.sha(roster),"environment":hist["environment"],"pytest_findpaths_sha":old.sha((old.PY.parents[1]/"Lib/site-packages/_pytest/config/findpaths.py").read_bytes())})
    print("selected",[(p["current"][:8],p["subject"],list(p["resources"]),p["remaining_force_all"],len(p["modules"])) for p in selected],flush=True)
if __name__=="__main__":main()
