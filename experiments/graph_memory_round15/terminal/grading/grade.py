"""Official independent R15 evaluator. Only sealed native solver results can select model patches."""
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pyarrow.parquet as pq

D=Path(__file__).resolve().parent
TASK=D.parent
RELEASE=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
R12=TASK.parents[1]/"graph_memory_round12/vibe/grading"
PRIVATE=Path("D:/CodexResearch/x20-r15-evaluator-inputs")
sys.path.insert(0,str(RELEASE/"scripts"))
import run_eval
from native_counts import check

MARKER=b"diff --git a/.vibe-calibration-marker b/.vibe-calibration-marker\nnew file mode 100644\n--- /dev/null\n+++ b/.vibe-calibration-marker\n@@ -0,0 +1 @@\n+calibration\n"
def h(b):return hashlib.sha256(b).hexdigest()
def hashed(data):return h(json.dumps(data,sort_keys=True,ensure_ascii=False,default=str,separators=(",",":")).encode())
def read(p):return json.loads(p.read_bytes())
def put(p,x):
    p.parent.mkdir(exist_ok=True,parents=True)
    tmp=p.with_suffix(".writing");tmp.write_text(json.dumps(x,indent=1,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf8")
    os.replace(tmp,p)
def docker(*args):
    return subprocess.run(["wsl.exe","-d","CodexX20MSR","--exec","docker",*args],check=True,capture_output=True,timeout=100).stdout
def get_context():
    for name,sig in read(TASK/"assignment.json").items():assert h((TASK/name).read_bytes())==sig
    cohort=read(TASK/"cohort.json")["targets"];ids=[r["instance_id"] for r in cohort]
    allspec={r["instance_id"]:r for r in pq.read_table(RELEASE/"benchmark/test.parquet",filters=[("instance_id","in",ids)]).to_pylist()}
    assert set(ids)==set(allspec)
    env={}
    for t in cohort:
        iid=t["instance_id"];spec=allspec[iid]
        assert all(spec[k]==t[k] for k in ("repo","base_commit","image_name"))
        image=json.loads(docker("image","inspect",t["image_name"]))[0]
        src=t["local_image"].split(" ",1)
        assert image["Id"]==src[0] and image["RepoDigests"]==json.loads(src[1])
        env[iid]=dict(image=image["Id"],registry=image["RepoDigests"],base=t["base_commit"],
            exact_spec_sha=hashed(spec),gold_sha=h(spec["patch"].encode()),test_patch_sha=h(spec["test_patch"].encode()),
            expected_f2p=spec["FAIL_TO_PASS"],expected_p2p=spec["PASS_TO_PASS"],test_config_sha=hashed(spec["install_config"]))
    code={str(p):h(p.read_bytes()) for p in [RELEASE/"scripts/run_eval.py",RELEASE/"scripts/vendor/eval.py",RELEASE/"scripts/vendor/log_parsers.py",RELEASE/"scripts/vendor/swe_constants.py",R12/"bridge.py",R12/"bin/docker"]}
    frozen={"goal":"terminal-state recovery; independent evaluator","assignment_sha":h((TASK/"assignment.json").read_bytes()),
            "official_code":code,"images":env,"policy":"no network, half a CPU, one evaluator at a time, release commands and parser",
            "docker_server":docker("version","--format","{{.Server.Version}}").decode().strip()}
    old=D/"environment.json"
    if old.exists():assert read(old)==frozen
    else:put(old,frozen)
    return cohort,allspec

def select(i):
    seed=TASK/"episodes/python"/i/"base/seed1";seal=seed/"seal.json"
    if not seal.exists():return None
    prior=read(seal)
    for n,sha in prior.items():assert h((seed/n).read_bytes())==sha
    c=read(seed/"capture.json");traj=seed/(i+".traj.json")
    official=run_eval._extract_patch_from_preds(seed);origin="preds.json"
    if official is None:official=run_eval._extract_patch_from_traj(traj);origin=traj.name
    if official is None:official=(i,"");origin="undiscoverable"
    assert official[0]==i
    b=official[1].encode();native=(read(traj)["info"].get("submission") or "").encode()
    assert h(native)==c["official_sha"] and len(native)==c["official_bytes"]
    terminal=None
    if c["rc"]==0:
        terminal=gzip.decompress((seed/"terminal.patch.gz").read_bytes())
        assert h(terminal)==c["sha"] and len(terminal)==c["bytes"]
    else:assert c["sha"] is None and c["bytes"] is None
    v=b if b.strip() else terminal if terminal is not None else b
    fallback="native_nonempty" if b.strip() else "captured" if terminal is not None else "capture_unavailable_native_empty"
    meta={"task":i,"seed":1,"seed_seal":h(seal.read_bytes()),"official_origin":origin,"trajectory_submission_matches_discovered":b==native,
          "fallback_policy":fallback,"fallback_equals_official":b==v,"native_bytes":len(b),"fallback_bytes":len(v),"terminal_bytes":None if terminal is None else len(terminal),
          "official_patch":h(b),"fallback_patch":h(v),"terminal_patch":None if terminal is None else h(terminal),
          "capture":c,"cleanup":read(seed/"cleanup.json"),"exit_status":read(traj)["info"].get("exit_status")}
    put(D/"selection"/(i+".json"),meta)
    return (("official",b),("fallback",v))
def evaluate(i,label,b,specs):
    sig=h(b);p=D/"grades"/i/sig;marker=p/"grade.json"
    if marker.exists():
        info=read(marker);assert info["task"]==i and info["sha"]==sig and (p/"patch.gz").is_file()
        assert gzip.decompress((p/"patch.gz").read_bytes())==b
        assert all(h((p/n).read_bytes())==v for n,v in info["outputs"].items())
        if info["unit_log"]:
            recomputed=check(read(p/"eval_report.json")["items"][0],specs[i],p/"unit.log")
            if info["score"]!=recomputed:info["score"]=recomputed;put(marker,info)
        return info
    wd=PRIVATE/i/sig
    if wd.exists():
        # Preserve failed attempts; choose a fresh input folder rather than modifying them.
        wd=wd.with_name(sig+"-retry"+str(time.time_ns()))
    wd.mkdir(exist_ok=False,parents=True)
    started=time.time()
    native=run_eval.evaluate_seed(run_eval.SeedRun(seed_dir=wd,instance_id=i,model_patch=b.decode("utf8")),specs,R12/"bridge.py",timeout=1800)
    observed=read(wd/"eval_input.json")[0]
    assert observed["patch"].encode()==b and observed["test_patch"].encode()==specs[i]["test_patch"].encode()
    p.mkdir(exist_ok=True,parents=True)
    (p/"patch.gz").write_bytes(gzip.compress(b,mtime=0))
    for name in ("eval_stdout.log","eval_stderr.log","container.log","eval_report.json"):
        if (wd/name).exists():shutil.copyfile(wd/name,p/name)
    ref=read(p/"eval_report.json")["items"][0] if (p/"eval_report.json").exists() else {}
    unit=None
    if ref.get("log_path"):
        unit=(wd/ref["log_path"]).resolve()
        assert unit.is_relative_to(wd.resolve())
        if unit.is_file():shutil.copyfile(unit,p/"unit.log")
    executed=(p/"unit.log").is_file()
    info={"task":i,"label_first_graded":label,"sha":sig,"bytes":len(b),"native":native,"input_sha":h((wd/"eval_input.json").read_bytes()),
          "image_name":specs[i]["image_name"],"evaluator_environment_sha":h((D/"environment.json").read_bytes()),"elapsed_s":time.time()-started,
          "unit_log":executed,"unit_exit":ref.get("exit_code"),"passed_match":ref.get("passed_match"),"vendor_error":ref.get("error"),
          "status":"no_patch" if not b.strip() else "harness_error" if native.get("error") else "resolved" if native["resolved"] else "unresolved",
          "expected_f2p":len(specs[i]["FAIL_TO_PASS"]),"expected_p2p":len(specs[i]["PASS_TO_PASS"]),
          "score":check(ref,specs[i],p/"unit.log") if executed else None,"outputs":{f.name:h(f.read_bytes()) for f in p.iterdir() if f.is_file() and f.name!="grade.json"}}
    put(marker,info);print(i,label,info["status"],info["score"],flush=True)
    return info
def main(mode):
    cohort,specs=get_context();indices=read(D/"index.json") if (D/"index.json").exists() else {}
    if mode in ("controls","all"):
        for label in ("gold","marker"):
            for t in cohort:
                i=t["instance_id"];bb=specs[i]["patch"].encode() if label=="gold" else MARKER
                res=evaluate(i,label,bb,specs);indices.setdefault(i,{})[label]=res["sha"];put(D/"index.json",indices)
    if mode in ("models","all"):
        for t in cohort:
            i=t["instance_id"];arr=select(i)
            if arr is None:print(i,"pending actual seal",flush=True);continue
            for label,bb in arr:
                res=evaluate(i,label,bb,specs);indices.setdefault(i,{})[label]=res["sha"];put(D/"index.json",indices)
if __name__=="__main__":main(sys.argv[1])
