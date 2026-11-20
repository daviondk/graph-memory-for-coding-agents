"""Actual public packaged binary and author MCP calls on 320 preselected new heldout issues."""
import os,json,subprocess,time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from data_io import *
from native_run import load_module

def run_config(config):
    wanted=read("paired_roster.json");selected=read("strict_roster.json")
    directory=D/"native_holdout"/config;directory.mkdir(parents=True,exist_ok=True)
    binary=D/"native/semlith.exe";model=D/"native/models"
    os.environ.update(dict(SEMLITH_BIN=str(binary),SEMLITH_HOME=str(directory/"home"),SEMLITH_MODEL_CACHE=str(model),
        SEMLITH_ACCEL="cpu",SEMLITH_EMBED_THREADS="3",SCORECARD_HOME=str(directory/"scorecard"),PYTHONUTF8="1"))
    load_module("common","publisher_common.py");arms=load_module("arms","publisher_arms.py")
    items=[];corpus=directory/"corpus";store=directory/"store"
    for p in files("java","test"):
        if not p.stem.startswith(config+"_test_"):continue
        panel=panel_name(p.stem);m={j:i for j,i in selected[p.stem] if i in wanted[panel]}
        for j,r in enumerate(rows(p,["code","context"])):
            if j in m:items.append((panel,m[j],r))
    assert len(items)==160
    for i,(_,_,r) in enumerate(items):
        fold=corpus/f"i{i:05d}";fold.mkdir(exist_ok=True,parents=True)
        for j,doc in enumerate(r["context"]):(fold/f"c{j:03d}.java").write_text(doc,encoding="utf8",newline="\n")
    t=time.monotonic()
    with (directory/"index.log").open("wb") as log:
        rs=subprocess.run([str(binary),"index","--store",str(store),str(corpus)],stdout=log,stderr=log,timeout=1600)
        if rs.returncode:raise RuntimeError((directory/"index.log").read_text("utf8",errors="replace")[-1400:])
    sec=time.monotonic()-t;t=time.monotonic()
    engine=arms.SemlithMCP(str(store));out=[]
    try:
        for i,(panel,idx,r) in enumerate(items):
            for keep in (3,10):
                q="\n".join(r["code"].splitlines()[-keep:]);hits=engine.search(q,k=len(r["context"])+10,paths=[f"i{i:05d}/**"])
                order=[]
                for e in hits:
                    path=Path(e.path);target=int(path.stem[1:])
                    assert path.stem[0]=="c" and 0<=target<len(r["context"])
                    if target not in order:order.append(target)
                rank=order+[j for j in range(len(r["context"])) if j not in order]
                out.append([panel,idx,keep,len(order),rank])
    finally:engine.close()
    write("paired_"+config+".json",out)
    return {"config":config,"index_s":sec,"query_s":time.monotonic()-t,"n":len(items),"output_sha":sha(D/("paired_"+config+".json"))}
def main():
    files_=["NATIVE_HOLDOUT_PROTOCOL.md","strict_select.py","strict_binary.py","strict_roster.json","paired_roster.json","native/semlith.exe","publisher_arms.py"]
    write("paired_method_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"files":{n:sha(D/n) for n in files_}})
    with ProcessPoolExecutor(2) as workers:result=list(workers.map(run_config,["java_cff","java_cfr"]))
    write("paired_decision_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"runs":result})
if __name__=="__main__":main()
