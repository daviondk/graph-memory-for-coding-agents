"""Use the pinned Semlith binary and publisher stdio RPC/terms definitions. Only pass inert source text to the indexer."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from data_io import D, files, rows, read, write, panel_name, sha

def load_module(mod,file):
    spec=importlib.util.spec_from_file_location(mod,D/file)
    module=importlib.util.module_from_spec(spec);sys.modules[mod]=module;spec.loader.exec_module(module);return module

def run():
    start=time.monotonic()
    n=D/"native"
    env=dict(SEMLITH_BIN=str(n/"semlith.exe"),SEMLITH_HOME=str(n/"home"),SEMLITH_MODEL_CACHE=str(n/"models"),
             SEMLITH_ACCEL="cpu",SEMLITH_EMBED_THREADS="2",PYTHONUTF8="1",SCORECARD_HOME=str(n/"scorecard"))
    os.environ.update(env)
    load_module("common","publisher_common.py");arms=load_module("arms","publisher_arms.py")
    native=read("native_roster.json");roster=read("roster.json")
    rows_by_config={}
    for p in files("java","test"):
        panel=panel_name(p.stem);subset={a:b for a,b in roster[p.stem] if b in native[panel]}
        for j,row in enumerate(rows(p,["code","context"])):
            if j in subset:
                key=panel.rsplit("_test_",1)[0]
                rows_by_config.setdefault(key,[]).append((panel,subset[j],row))
    predictions=[];status=[]
    for config,items in rows_by_config.items():
        corpus=n/"corpus"/config;store=n/"stores"/config
        for i,(_,_,row) in enumerate(items):
            folder=corpus/f"i{i:05d}";folder.mkdir(parents=True,exist_ok=True)
            for j,s in enumerate(row["context"]):(folder/f"c{j:03d}.java").write_text(s,encoding="utf8",newline="\n")
        command=[env["SEMLITH_BIN"],"index","--store",str(store),str(corpus)]
        started=time.monotonic()
        with (n/(config+".log")).open("wb") as log:
            pr=subprocess.run(command,stdout=log,stderr=log,timeout=1200)
        assert pr.returncode==0,(n/(config+".log")).read_text("utf8",errors="replace")[-2000:]
        status.append({"config":config,"seconds_index":time.monotonic()-started,"items":len(items)})
        engine=arms.SemlithMCP(str(store))
        try:
            for i,(panel,j,row) in enumerate(items):
                for keep in (3,10):
                    query="\n".join(row["code"].splitlines()[-keep:]);candidates=row["context"]
                    hits=engine.search(query,k=len(candidates)+10,paths=[f"i{i:05d}/**"])
                    order=[]
                    for match in hits:
                        path=Path(match.path);target=int(path.stem[1:]);assert 0<=target<len(candidates) and path.stem[0]=="c"
                        if target not in order:order.append(target)
                    ranking=order+[x for x in range(len(candidates)) if x not in order]
                    predictions.append([panel,j,keep,len(order),ranking])
        finally:engine.close()
        write("native_partial.json",predictions)
    write("native_predictions.json",predictions)
    write("native_receipt.json",{"binary_sha256":sha(n/"semlith.exe"),"publisher_sha256":sha(D/"publisher_arms.py"),"env":env,
         "variant":"public CPU index on 24 chosen per stratum, samples within configuration indexed together","status":status,"seconds":time.monotonic()-start})
if __name__=="__main__":run()
