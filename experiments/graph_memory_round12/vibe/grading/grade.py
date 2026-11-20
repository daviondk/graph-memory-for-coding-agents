"""Isolated, restartable official evaluator sidecar; no solver inputs are written to its directory."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
import pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent;VIBE=HERE.parent
REL=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
PRIVATE=Path("D:/CodexResearch/x20-r12-evaluator-inputs")
sys.path.insert(0,str(REL/"scripts"))
import run_eval
marker="diff --git a/.vibe-calibration-marker b/.vibe-calibration-marker\nnew file mode 100644\n--- /dev/null\n+++ b/.vibe-calibration-marker\n@@ -0,0 +1 @@\n+calibration\n"
cohort=json.loads((VIBE/"cohort.json").read_bytes())["targets"]
ids=[t["instance_id"] for t in cohort];methods=("base","raw","graph")
specs={x["instance_id"]:x for x in pq.read_table(REL/"benchmark/test.parquet",filters=[("instance_id","in",ids)]).to_pylist()}
assert set(specs)==set(ids)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(path,obj):
    path.parent.mkdir(exist_ok=True,parents=True)
    tmp=path.with_suffix(".writing");tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf8");os.replace(tmp,path)
def load(p):return json.loads(p.read_bytes())
def seed(i,m):return VIBE/"episodes/python"/i/m/"seed0"
def done(i,m):return HERE/("controls" if m in ("gold","marker") else "models")/i/m/"result.json"
def patch_for(i,m):
    if m=="gold":return specs[i]["patch"],"public gold calibration",None
    if m=="marker":return marker,"nonfunctional marker calibration",None
    s=seed(i,m);f=s/"finished.json"
    if not f.exists():return None
    tr=s/(i+".traj.json")
    patch=run_eval._extract_patch_from_preds(s);origin=s/"preds.json"
    if patch is None:patch=run_eval._extract_patch_from_traj(tr);origin=tr
    if patch is None:return "","undiscoverable completed episode",sha(f.read_bytes())
    assert patch[0]==i
    return patch[1],origin.name,sha(f.read_bytes())
def run(i,m):
    output=done(i,m);incoming=patch_for(i,m)
    if incoming is None:return False
    patch,origin,finished_sha=incoming
    if output.is_file():
        r=load(output)
        if r["patch_sha"]!=sha(patch.encode()):raise RuntimeError("Previously graded episode changed")
        return True
    wd=PRIVATE/i/m
    if wd.exists():raise RuntimeError(f"Existing uncompleted result in grader directory: {wd}")
    wd.mkdir(parents=True)
    info=run_eval.evaluate_seed(run_eval.SeedRun(seed_dir=wd,instance_id=i,model_patch=patch),specs,HERE/"bridge.py",timeout=1800)
    out=output.parent;out.mkdir(exist_ok=True,parents=True)
    for n in ("eval_stdout.log","eval_stderr.log","container.log"):
        if (wd/n).is_file():shutil.copyfile(wd/n,out/n)
    rep=wd/"eval_report.json";item=load(rep)["items"][0] if rep.is_file() else {}
    if rep.is_file():shutil.copyfile(rep,out/"native-report.json")
    if item.get("log_path"):
        lg=(wd/item["log_path"]).resolve();assert lg.is_relative_to(wd)
        if lg.is_file():shutil.copyfile(lg,out/"unit.log")
    from_to=item.get("from_fail_to_pass",[]);lost=item.get("failed_from_pass_to_pass",[])
    result=dict(instance=i,method=m,source=origin,finish_sha=finished_sha,patch_sha=sha(patch.encode()),patch_bytes=len(patch.encode()),
            official=info,passed_match=item.get("passed_match"),unit_exit=item.get("exit_code"),vendor_error=item.get("error"),
            confirmed_F2P=len(from_to),expected_F2P=len(specs[i]["FAIL_TO_PASS"]),lost_P2P=len(lost),
            expected_P2P=len(specs[i]["PASS_TO_PASS"]),status=("no_patch" if not patch.strip() else "harness_error" if info.get("error") else "resolved" if info["resolved"] else "unresolved"),
            hashes={f.name:sha(f.read_bytes()) for f in out.iterdir() if f.is_file()})
    put(output,result)
    print(i,m,result["status"],result["confirmed_F2P"],result["expected_F2P"],result["lost_P2P"],flush=True)
    return True
def main():
    ap=argparse.ArgumentParser();ap.add_argument("action",choices=("watch","once","one","controls"));ap.add_argument("--iid",choices=ids);ap.add_argument("--method",choices=methods+("gold","marker"))
    a=ap.parse_args();order=load(VIBE/"order.json");controls=[(i,m) for m in ("gold","marker") for i in ids]
    if a.action=="one":
        if not a.iid or not a.method:ap.error("specify --iid and --method")
        if not run(a.iid,a.method):print("Pending episode")
        return
    if a.action=="controls":
        for i,m in controls:run(i,m)
        return
    while True:
        for i,m in order+controls:
            if not done(i,m).is_file() and patch_for(i,m) is not None:
                run(i,m);break
        else:
            if a.action=="once" or all(done(i,m).is_file() for i,m in order+controls):break
            time.sleep(8)
if __name__=="__main__":main()
