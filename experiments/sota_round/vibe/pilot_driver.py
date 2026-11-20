"""Call VibeMemBench.run_instance unchanged, with paired local endpoints and a safe solver-only parquet."""
import json
import os
import subprocess
import shutil
import uuid
from datetime import datetime, timezone
import sys
from argparse import Namespace
from pathlib import Path

import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ["VIBE_RELEASE"]).resolve()
STORE = ROOT.parent / "solver-runtime"
sys.path.insert(0, str(ROOT / "scripts"))
import run_agent

cohort = json.loads((HERE / "cohort.json").read_text(encoding="utf8"))
targets = {t["instance_id"]: t for t in cohort["targets"]}
protocol_path = Path(os.environ.get("VIBE_SOLVER_PROTOCOL", HERE/"amendment_8b.json"))
protocol = json.loads(protocol_path.read_text(encoding="utf8"))
output = ROOT / "outputs" / protocol["runs_subdir"]
subset = STORE / "pilot_solver_subset"
subset.mkdir(exist_ok=True)
source = ROOT / "benchmark" / "test.parquet"
safe_fields = ["instance_id", "repo", "language", "problem_statement", "image_name", "base_commit"]
safe = pq.read_table(source, columns=safe_fields, filters=[("instance_id","in", list(targets))])
assert set(safe["instance_id"].to_pylist()) == set(targets)
pq.write_table(safe, subset / "test.parquet")
methods = protocol["methods"]
memory = {m: run_agent._load_memory_texts(ROOT / "outputs" / "memory", m) for m in methods[2:]}
env_base = dict(os.environ,
    VIBE_COHORT=str(HERE / "cohort.json"), PYTHONUTF8="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
    HF_HOME=str(STORE / "hf-cache"), HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1",
    MSWEA_GLOBAL_CONFIG_DIR=str(STORE / "mini-config"), MSWEA_SILENT_STARTUP="1",
    MSWEA_COST_TRACKING="ignore_errors", LITELLM_LOCAL_MODEL_COST_MAP="True",
    MSWEA_DOCKER_EXECUTABLE=str(Path(sys.executable).parent / "vibe-local-docker.exe"),
    PYTHONPATH=str(ROOT / "mini-swe-agent" / "src"),
    TEMP=str(STORE / "tmp"), TMP=str(STORE / "tmp"),
)
for k in ["HF_HOME","MSWEA_GLOBAL_CONFIG_DIR","TEMP"]:
    Path(env_base[k]).mkdir(parents=True,exist_ok=True)

def one(iid,seed,method):
    args = Namespace(_iid_to_lang={iid:"python"}, output=output, method=method, _subset_dir=subset,
        split="test",model=protocol["solver"],api_base=protocol["endpoint"].format(seed=seed,iid=iid,method=method,attempt=uuid.uuid4().hex),
        api_key="local",temperature=protocol["temperature"],cost_limit=3.0,step_limit=protocol["step_limit"],pull_timeout=1800,
        _distractor_text=run_agent._DEFAULT_DISTRACTOR_TEXT.strip(),_memory_by_iid=memory.get(method,{}),dry_run=False)
    sd = run_agent._seed_dir(output,iid,seed,lang="python",method=method)
    sd.mkdir(parents=True,exist_ok=True)
    if run_agent._traj_exists(sd,iid):return {"status":"alreadyfinished","iid":iid,"method":method,"seed":seed}
    if (sd / "run.log").is_file():
        # Preserve every mid-episode interruption before starting a fresh container.
        archive_root = "interrupted" if protocol["runs_subdir"] == "pilot_agent" else protocol["runs_subdir"] + "_interrupted"
        archive = STORE / archive_root / sd.relative_to(output) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sd), str(archive))
        sd.mkdir(parents=True)
    receipt = sd / "container_id.txt"
    env = {**env_base,"VIBE_CONTAINER_RECEIPT":str(receipt)}
    result = run_agent.run_instance(iid,seed,args=args,env=env)
    if receipt.is_file():
        cid=receipt.read_text().strip()
        if len(cid)==64 and all(c in "0123456789abcdef" for c in cid):
            subprocess.run(["wsl.exe","-d","CodexX20MSR","--exec","/usr/bin/docker","rm","-f",cid],capture_output=True)
    if not run_agent._traj_exists(sd,iid):
        raise RuntimeError(f"Unfinished infrastructure run {iid}/{method}/seed{seed}, see run.log")
    return result

# The restart runs one host worker at a time, preserving the paired endpoints.
for seed in protocol["planned_seeds"]:
    for iid in targets:
        for method in methods:
            print(json.dumps(one(iid,seed,method)),flush=True)
