"""Choose native regression tests before any runs, lock graph predictions, then perform genuine paired rollbacks."""
import ast
import collections
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from observe import ROOT, put, read, sha

GIT=Path("D:/CodexResearch/x20-round17-test-history")
CACHE=Path("D:/CodexResearch/x20-round17-test-rollbacks")
MODULES={"more_itertools/more.py","more_itertools/recipes.py"}
VERSIONS=("v10.6.0","v10.8.0")
def git(*args):return subprocess.check_output(["git","-C",str(GIT),*args])
def source(commit,file):return git("show",f"{commit}:{file}")
def structure(data):
    module=ast.parse(data);defs=(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)
    top={n.name:ast.dump(n,include_attributes=False) for n in module.body if isinstance(n,defs)}
    outer=[ast.dump(n) for n in module.body if not isinstance(n,defs)]
    return top,outer
def methods(data,file):
    module=ast.parse(data)
    found={}
    prefix=file.removesuffix(".py").replace("/",".")
    for c in module.body:
        if isinstance(c,ast.ClassDef):
            for n in c.body:
                if isinstance(n,ast.FunctionDef) and n.name.startswith("test"):
                    ref=prefix+"."+c.name+"."+n.name
                    words={node.id for node in ast.walk(n) if isinstance(node,ast.Name)}
                    words.update(node.attr for node in ast.walk(n) if isinstance(node,ast.Attribute))
                    found[ref]={"ast":sha(ast.dump(n).encode()),"names":sorted(words)}
    return found
def prepare():
    tags={t:git("rev-parse",t+"^{commit}").decode().strip() for t in VERSIONS}
    commits=git("rev-list","--no-merges",tags[VERSIONS[0]]+".."+tags[VERSIONS[1]]).decode().split()
    eligible=[];skipped=collections.Counter()
    for commit in sorted(commits,key=lambda s:sha(("r17s:"+s).encode())):
        parent=git("rev-parse",commit+"^").decode().strip()
        subject=git("log","-1","--format=%s",commit).decode().strip()
        if re.search(r"vulnerab|security|exploit|cve-\d",subject,re.I):continue
        files=git("diff","--name-only",parent,commit).decode().splitlines()
        mod=[f for f in files if f in MODULES]; tests=[f for f in files if re.fullmatch(r"tests/test_\w+\.py",f)]
        if len(mod)!=1 or not tests:continue
        f=mod[0]
        if any(x.startswith("more_itertools/") and x.endswith(".py") and x!=f for x in files):continue
        after,outer=structure(source(commit,f));before,old_outer=structure(source(parent,f))
        if after.keys()!=before.keys() or outer!=old_outer:continue
        changed=sorted(k for k in after if after[k]!=before[k])
        if not changed:continue
        test_tree=[s for s in git("ls-tree","-r","--name-only",commit,"tests").decode().splitlines() if re.fullmatch(r"tests/test_\w+.py",s)]
        new={};old={}
        for file in test_tree:
            new.update(methods(source(commit,file),file))
            try: old.update(methods(source(parent,file),file))
            except subprocess.CalledProcessError:pass
        hit=[k for k in new if k not in old or new[k]["ast"]!=old[k]["ast"]]
        control=[k for k in new if k not in hit]
        if not hit:continue
        sk=lambda name:sha(("r17u:"+commit+":"+name).encode())
        chosen=[{"name":k,"changed_test":label,"direct_lexical":bool(set(new[k]["names"])&set(changed))} for label,keys,cap in [(True,hit,4),(False,control,8)] for k in sorted(keys,key=sk)[:cap]]
        eligible.append({"commit":commit,"parent":parent,"subject":subject,"module":f,"changed":changed,"tests":chosen,"before_sha":sha(source(parent,f)),"after_sha":sha(source(commit,f)),"testfile_sha":{p:sha(source(commit,p)) for p in test_tree}})
    chosen=eligible[:8]
    put("rollback-roster.json",{"tags":tags,"eligible":len(eligible),"count":len(chosen),"blocks":chosen,"python":sys.version,"repository":"https://github.com/more-itertools/more-itertools"})
    put("rollback-lock.json",{n:sha((ROOT/n).read_bytes()) for n in ("rollback-roster.json","ROLLBACK_PROTOCOL_RU.md","rollback.py","runner.py")})
    print("eligible",len(eligible),[(r["commit"][:8],len(r["tests"])) for r in chosen])
def build(block,dir):
    dir.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(git("-c","core.autocrlf=false","archive",block["commit"])),mode="r:") as tar:tar.extractall(dir,filter="data")
    for f,h in block["testfile_sha"].items():assert sha((dir/f).read_bytes())==h
def run(block,stage,rep,trace):
    cwd=CACHE/block["commit"]/stage;data=CACHE/block["commit"]/("jobs-"+stage+".json")
    data.write_text(json.dumps(block["tests"]),encoding="utf8")
    c=subprocess.run([sys.executable,"-B",ROOT/"runner.py",data,"trace" if trace else "plain"],cwd=cwd,env={**os.environ,"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1"},capture_output=True,timeout=150)
    if c.returncode:raise RuntimeError(c.stderr.decode(errors="replace")[-1700:])
    return {"stage":stage,"repeat":rep,"trace":trace,"answers":json.loads(c.stdout),"stderr":c.stderr.decode(errors="replace")}
def main():
    if len(sys.argv)>1 and sys.argv[1]=="prepare":prepare();return
    for n,h in read(ROOT/"rollback-lock.json").items():assert sha((ROOT/n).read_bytes())==h
    blocks=read(ROOT/"rollback-roster.json")["blocks"]
    before={};predictions=[]
    for b in blocks:
        c=b["commit"];cwd=CACHE/c/"child";build(b,cwd);assert sha((cwd/b["module"]).read_bytes())==b["after_sha"]
        runs=[run(b,"child",i,i==0) for i in range(2)];before[c]=runs
        for case in b["tests"]:
            name=case["name"];a=runs[0]["answers"][name];status=[r["answers"][name]["outcome"] for r in runs]
            if status!=["pass","pass"]:continue
            tested_fns={fn for file,fn in a["calls"] if file==b["module"]}
            predictions.append({"commit":c,"name":name,"edited_test":case["changed_test"],"module":b["module"],"changed":b["changed"],"observed_functions":sorted(tested_fns),"accepted":{
                "rerun_all":False,"reuse_all":True,"lexical":not case["direct_lexical"],"dynamic_file":b["module"] not in a["files"],"dynamic_function":not tested_fns.intersection(b["changed"])}})
    put("rollback-child.gz",before);put("rollback-forecasts.gz",predictions)
    put("rollback-forecast-seal.json",{n:sha((ROOT/n).read_bytes()) for n in ("rollback-lock.json","rollback-child.gz","rollback-forecasts.gz")})
    after={};rows=[]
    for b in blocks:
        c=b["commit"];cwd=CACHE/c/"rollback";build(b,cwd);(cwd/b["module"]).write_bytes(source(b["parent"],b["module"]))
        assert sha((cwd/b["module"]).read_bytes())==b["before_sha"]
        after[c]=[run(b,"rollback",i,False) for i in range(2)]
    for pred in predictions:
        values=[r["answers"][pred["name"]]["outcome"] for r in after[pred["commit"]]]
        rows.append({**pred,"actual":values[0] if values[0]==values[1] else "unstable","repeats":values})
    put("rollback-runs.gz",after);put("rollback-graded.gz",rows)
    groups={"all":rows,"changed_test":[p for p in rows if p["edited_test"]],"unchanged_test":[p for p in rows if not p["edited_test"]]}
    scores={}
    for group,rs in groups.items():
        metrics={}
        for arm in ("rerun_all","reuse_all","lexical","dynamic_file","dynamic_function"):
            use=[p for p in rs if p["accepted"][arm]]
            metrics[arm]={"reuse":len(use),"rerun":len(rs)-len(use),"use_outcomes":collections.Counter(p["actual"] for p in use)}
        scores[group]={"pairs":len(rs),"outcomes":collections.Counter(p["actual"] for p in rs),"arms":metrics}
    scores["by_commit"]={b["commit"]:{"n":sum(p["commit"]==b["commit"] for p in rows),"fails":sum(p["commit"]==b["commit"] and p["actual"]=="fail" for p in rows)} for b in blocks}
    put("rollback-results.json",scores);print(scores["all"],scores["by_commit"])
if __name__=="__main__":main()
