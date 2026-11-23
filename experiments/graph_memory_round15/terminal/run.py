"""Paired final submission and single pull of tracked state after native solver termination."""
import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
RELEASE=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
sys.path.insert(0,str(RELEASE/"scripts"))
import run_agent
IMAGES=["docker.io/swerebenchv2/brazilian-utils-brutils-python:125-9046eed","docker.io/swerebenchv2/s-knibbs-dataclasses-jsonschema:64-dad240e"]
FIELDS=["instance_id","repo","language","problem_statement","image_name","base_commit"]
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,x):
    dest=ROOT/name;dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(x,indent=1,ensure_ascii=False)+"\n",encoding="utf8")
def load(name):return json.loads((ROOT/name).read_bytes())
def docker(args,timeout=90):
    return subprocess.run(["wsl","-d","CodexX20MSR","--exec","docker",*args],capture_output=True,timeout=timeout)
def prepare():
    tab=pq.read_table(RELEASE/"benchmark/test.parquet",columns=FIELDS)
    allrows=tab.to_pylist()
    rows=[r for r in allrows if r["image_name"].removeprefix("docker.io/") in {i.removeprefix("docker.io/") for i in IMAGES}]
    assert len(rows)==2
    (ROOT/"subset").mkdir(exist_ok=True)
    sel=tab.filter(__import__("pyarrow").array([r in rows for r in allrows]))
    pq.write_table(sel,ROOT/"subset/test.parquet")
    targets=[]
    for r in rows:
        inspected=docker(["image","inspect","--format","{{.Id}} {{json .RepoDigests}}",r["image_name"]])
        assert inspected.returncode==0,inspected.stderr
        targets.append({**{k:v for k,v in r.items() if k!="problem_statement"},"local_image":inspected.stdout.decode().strip()})
    save("cohort.json",{"targets":targets,"method":"base","replicate":1,"max_calls":24})
    save("assignment.json",{n:sha((ROOT/n).read_bytes()) for n in ["run.py","seed_proxy.py","PROTOCOL_RU.md","cohort.json","subset/test.parquet"]})
    print([t["instance_id"] for t in targets])
def run():
    for n,h in load("assignment.json").items():assert sha((ROOT/n).read_bytes())==h
    runtime=RELEASE.parent/"solver-runtime"
    env=dict(os.environ,VIBE_COHORT=str(ROOT/"cohort.json"),PYTHONUTF8="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
        HF_HOME=str(runtime/"hf-cache"),HF_HUB_OFFLINE="1",HF_DATASETS_OFFLINE="1",MSWEA_GLOBAL_CONFIG_DIR=str(runtime/"mini-config"),
        MSWEA_SILENT_STARTUP="1",MSWEA_COST_TRACKING="ignore_errors",LITELLM_LOCAL_MODEL_COST_MAP="True",
        MSWEA_DOCKER_EXECUTABLE=str(Path(sys.executable).parent/"vibe-local-docker.exe"),
        PYTHONPATH=str(RELEASE/"mini-swe-agent/src"),TEMP=str(runtime/"tmp"),TMP=str(runtime/"tmp"))
    targets=sorted(load("cohort.json")["targets"],key=lambda q:sha(("r15/"+q["instance_id"]).encode()))
    for target in targets:
        i=target["instance_id"];out=ROOT/"episodes"
        args=argparse.Namespace(_iid_to_lang={i:"python"},output=out,method="base",_subset_dir=ROOT/"subset",split="test",
           model="openai/qwen38-27b-ud-q4km",api_base="http://127.0.0.1:18955/replicate/1/v1",api_key="local",
           temperature=.5,cost_limit=3.,step_limit=24,pull_timeout=300,_distractor_text="",_memory_by_iid={},dry_run=False)
        sd=run_agent._seed_dir(out,i,1,lang="python",method="base");sd.mkdir(parents=True,exist_ok=True)
        if (sd/"seal.json").is_file():continue
        if (sd/"container_id.txt").exists():raise RuntimeError("Inspect interrupted episode before trying again")
        receipt=sd/"container_id.txt"
        result=run_agent.run_instance(i,1,args=args,env={**env,"VIBE_CONTAINER_RECEIPT":str(receipt)})
        assert result["status"]=="ok" and receipt.exists(), result
        cid=receipt.read_text().strip();assert re.fullmatch("[0-9a-f]{64}",cid)
        t=time.time();git=docker(["exec",cid,"git","--no-optional-locks","-C","/testbed","diff","--no-ext-diff","--no-textconv","--binary","--no-color","HEAD","--"])
        elapsed=time.time()-t
        key=sd.relative_to(ROOT).as_posix();native=sd/(i+".traj.json")
        assert native.is_file()
        std=json.loads(native.read_bytes())["info"].get("submission") or ""
        assert isinstance(std,str)
        if git.returncode==0:(sd/"terminal.patch.gz").write_bytes(gzip.compress(git.stdout,mtime=0))
        save(key+"/capture.json",dict(rc=git.returncode,stderr=git.stderr.decode(errors="replace"),bytes=len(git.stdout) if git.returncode==0 else None,
                  sha=sha(git.stdout) if git.returncode==0 else None,seconds=elapsed,after_native_s=t-result["end_ts"],
                  official_bytes=len(std.encode()),official_sha=sha(std.encode()),result=result))
        removal=docker(["rm","-f",cid]);save(key+"/cleanup.json",dict(rc=removal.returncode,stdout=removal.stdout.decode(errors="replace"),stderr=removal.stderr.decode(errors="replace")))
        save(key+"/seal.json",{n.name:sha(n.read_bytes()) for n in sd.iterdir() if n.is_file()})
        print(i,"capture",git.returncode,len(git.stdout),"official",len(std.encode()),flush=True)
if __name__=="__main__":{"prepare":prepare,"run":run}[sys.argv[1]]()
