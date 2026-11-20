"""Run six preregistered episodes via author's entry point; write all attempts separately."""
import collections,json,os,subprocess,sys
from argparse import Namespace
from pathlib import Path
from memory import ROOT, RELEASE, WORK, sha, save
import run_agent
def main():
    for name,digest in json.loads((ROOT/"assignment-lock.json").read_bytes()).items():
        assert sha((ROOT/name).read_bytes())==digest
    cohort=json.loads((ROOT/"cohort.json").read_bytes())
    runtime=RELEASE.parent/"solver-runtime"
    env=dict(os.environ,VIBE_COHORT=str(ROOT/"cohort.json"),PYTHONUTF8="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
        HF_HOME=str(runtime/"hf-cache"),HF_HUB_OFFLINE="1",HF_DATASETS_OFFLINE="1",
        MSWEA_GLOBAL_CONFIG_DIR=str(runtime/"mini-config"),MSWEA_SILENT_STARTUP="1",MSWEA_COST_TRACKING="ignore_errors",
        LITELLM_LOCAL_MODEL_COST_MAP="True",MSWEA_DOCKER_EXECUTABLE=str(Path(sys.executable).parent/"vibe-local-docker.exe"),
        PYTHONPATH=str(RELEASE/"mini-swe-agent/src"),TEMP=str(runtime/"tmp"),TMP=str(runtime/"tmp"))
    plan=sorted(((r["instance_id"],m) for r in cohort["targets"] for m in ("base","raw","graph")),key=lambda k:sha(("r12|"+str(k)).encode()))
    save("order.json",plan)
    for iid,m in plan:
        out=ROOT/"episodes";seed=0
        args=Namespace(_iid_to_lang={iid:"python"},output=out,method=m,_subset_dir=ROOT/"subset",split="test",
           model="openai/qwen38-27b-ud-q4km",api_base="http://127.0.0.1:18951/replicate/0/v1",api_key="local",temperature=.5,
           cost_limit=3.,step_limit=cohort["steps"],pull_timeout=300,_distractor_text="",_memory_by_iid={} if m=="base" else
           {iid:(ROOT/"memories"/m/"python"/iid/"memory.txt").read_text(encoding="utf8")},dry_run=False)
        sd=run_agent._seed_dir(out,iid,seed,lang="python",method=m);sd.mkdir(parents=True,exist_ok=True)
        if (sd/"finished.json").is_file():continue
        receipt=sd/"container_id.txt"
        result=run_agent.run_instance(iid,seed,args=args,env={**env,"VIBE_CONTAINER_RECEIPT":str(receipt)})
        if receipt.exists():
            cid=receipt.read_text().strip()
            assert len(cid)==64 and all(c in "0123456789abcdef" for c in cid)
            subprocess.run(["wsl","-d","CodexX20MSR","--exec","docker","rm","-f",cid],capture_output=True)
        if result["status"]!="ok" or not (sd/(iid+".traj.json")).is_file():raise RuntimeError("Vibe execution "+str((iid,m,result)))
        (sd/"finished.json").write_text(json.dumps(result,indent=2)+"\n")
        print(iid,m,result["duration_s"],flush=True)
if __name__=="__main__":main()
