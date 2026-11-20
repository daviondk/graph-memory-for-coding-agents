"""Fresh SQLite DB per scenario, distinct timestamps, positive control, independent pytest without the plugin."""
from contextlib import closing
import concurrent.futures
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from collect import ROOT,AGENT,SCRATCH,read,save,digest,patch
from testmon.process_code import Module, match_fingerprint, blob_to_checksums
ID="sympy__sympy-20590"
NODE="sympy/core/tests/test_basic.py::test_immutable"
SOURCE="sympy/core/_print_helpers.py"
TEST=NODE.split("::")[0]
OUT=ROOT/"immutable_audit_final"
OUT.mkdir(exist_ok=True)
def snapshot(root,out,tag):
    db=root/".testmondata";dest=out/(tag+".sqlite")
    with closing(sqlite3.connect("file:"+db.as_posix()+"?mode=ro",uri=True)) as live,closing(sqlite3.connect(dest)) as copy:
        live.backup(copy)
        deps=copy.execute("""SELECT e.test_name,f.filename,hex(f.method_checksums),f.mtime,f.fsha
            FROM test_execution e JOIN test_execution_file_fp l ON l.test_execution_id=e.id JOIN file_fp f ON f.id=l.fingerprint_id WHERE e.test_name LIKE ? ORDER BY f.filename""",("%test_immutable",)).fetchall()
        sources=copy.execute("SELECT filename,hex(method_checksums),mtime,fsha FROM file_fp WHERE filename LIKE '%_print_helpers.py'").fetchall()
    assert deps
    return deps,sources
def command(root,nodes,out,tag):
    cmd=[sys.executable,"-B",str(ROOT/"testmon_runner.py"),str(nodes),str(out/(tag+".json"))]
    env={**os.environ,"PYTHONPATH":os.pathsep.join((str(SCRATCH/"testmon"),str(root))),"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"}
    p=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
    (out/(tag+".log")).write_bytes(p.stdout);assert p.returncode==0
    return read(out/(tag+".json"))
def solo(root,out):
    p=subprocess.run([sys.executable,"-B","-m","pytest","-q","-o","addopts=","--tb=line",NODE],cwd=root,
        env={**os.environ,"PYTHONPATH":str(root),"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"},
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    (out/"independent.log").write_bytes(p.stdout);assert p.returncode in [0,1];return p.returncode
def one(mode):
    origin=AGENT/"tasks"/ID;cfg=read(origin/"grading.json")
    out=OUT/mode;out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="immutable-",dir=SCRATCH) as temp:
        root=Path(temp)/"repo"
        shutil.copytree(origin/"base",root,ignore=shutil.ignore_patterns("__pycache__",".pytest_cache",".git","*.pyc",".testmondata*"))
        patch(root,cfg["test_patch"]);source=root/SOURCE;test=root/TEST;before=source.read_bytes()
        if mode!="single_fix":patch(root,cfg["patch"])
        watch=test if mode=="edited_test" else source
        stamp=1650000000
        os.utime(watch,(stamp,stamp))
        data=read(ROOT/"runs"/ID/"nodes.json")
        ordered=list(reversed(data)) if mode=="reverse_order_revert" else [NODE]
        nodes=out/"nodes.json";save(nodes,ordered)
        old=watch.read_bytes();rel=watch.relative_to(root).as_posix()
        build=command(root,nodes,out,"build");deps,whole=snapshot(root,out,"build")
        if mode=="single_fix":patch(root,cfg["patch"])
        elif mode=="edited_test":
            st=test.read_text("utf8");old_test="    assert not hasattr(b1, '__dict__')"
            assert st.count(old_test)==1;test.write_text(st.replace(old_test,"    assert 2 == 3",1),encoding="utf8")
        elif mode!="touch_only":source.write_bytes(before)
        os.utime(watch,(stamp+200,stamp+200))
        new=watch.read_bytes();assert (old!=new)==(mode!="touch_only") and watch.stat().st_mtime==stamp+200
        selected=command(root,nodes,out,"select")
        visited=[f for f in deps if f[1].replace("\\","/").endswith(rel)]
        module=Module(source_code=new.decode("utf8"),ext="py")
        still_match=[bool(match_fingerprint(module,blob_to_checksums(bytes.fromhex(row[2])))) for row in visited]
        details=dict(mode=mode,test=NODE,order=ordered,old_sha256=digest(old),new_sha256=digest(new),mtime_before=stamp,mtime_after=watch.stat().st_mtime,
                     sqlite_file_total=len(deps),legacy_test_file_edges=[f[1] for f in deps],changed_target=rel,
                     tracked_fingerprints_for_target=visited,old_fingerprint_matches_new_source=still_match,all_print_module_signatures=whole,
                     prior=build["reports"].get(NODE),plugin_after=selected["reports"].get(NODE),direct_pytest_after=solo(root,out),plugin_rc_after=selected["code"],
                     build_db_sha256=digest((out/"build.sqlite").read_bytes()))
        save(out/"details.json",details)
        return {k:v for k,v in details.items() if k not in ["legacy_test_file_edges","all_print_module_signatures","tracked_fingerprints_for_target"]}
if __name__=="__main__":
    modes=["single_revert","single_fix","reverse_order_revert","edited_test","touch_only"]
    with concurrent.futures.ThreadPoolExecutor(2) as ex:list(ex.map(one,[m for m in modes if not (OUT/m/"details.json").is_file()]))
    rows=[{k:v for k,v in read(OUT/m/"details.json").items() if k not in ["legacy_test_file_edges","all_print_module_signatures","tracked_fingerprints_for_target"]} for m in modes]
    save(OUT/"results.json",rows);print([(r["mode"],r["plugin_after"],r["direct_pytest_after"]) for r in rows])
