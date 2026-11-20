"""Verify the fixed assignment against official reports and export compact evidence without the source dataset."""
import csv
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
import zipfile


HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ["VIBE_RELEASE"]).resolve()
STORE=ROOT.parent/"solver-runtime"
protocol_path=Path(os.environ.get("VIBE_SOLVER_PROTOCOL", HERE/"amendment_8b.json"))
protocol=json.loads(protocol_path.read_text(encoding="utf8"))
RUNS=ROOT/"outputs"/protocol["runs_subdir"]
EXPORT=HERE if protocol["runs_subdir"]=="pilot_agent" else HERE/("in_loop" if protocol["runs_subdir"]=="pilot_in_loop" else "qwen38_27b")
EXPORT.mkdir(parents=True,exist_ok=True)
METHODS=tuple(protocol["methods"])
COHORT=json.loads((HERE/"cohort.json").read_text(encoding="utf8"))
ids=[t["instance_id"] for t in COHORT["targets"]]
checks=json.loads((HERE/"checker_controls.json").read_text(encoding="utf8"))
expected_tests={x["target"]:(x["expected_F2P"],x["expected_P2P"]) for x in checks}
assert all(x["passed_match"]==(x["control"]=="gold") for x in checks)
def load(p):return json.loads(p.read_text(encoding="utf8"))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def consumption(traj):
    calls=[m["extra"]["response"]["usage"] for m in traj.get("messages",[])
           if m.get("extra",{}).get("response",{}).get("usage")]
    return len(calls),sum(x["prompt_tokens"] for x in calls),sum(x["completion_tokens"] for x in calls),max([x["completion_tokens"] for x in calls] or [0])

with (RUNS/"eval_summary.csv").open(encoding="utf-8-sig") as f:
    evaluated={Path(row["seed_dir"]).resolve():row for row in csv.DictReader(f)}
expected_assignments=len(ids)*len(METHODS)*len(protocol["planned_seeds"])
assert len(evaluated)==expected_assignments,(len(evaluated),expected_assignments)
rows=[]
exact_rows={}
exact_path=(STORE/"portable-evidence"/"exact_usage.json") if EXPORT==HERE else EXPORT/"exact_usage.json"
exact_csv=exact_path.with_name("episode_calls.csv")
if exact_path.is_file():
    exact=load(exact_path)
    exact_rows={(r["target"],r["arm"],r["seed"]):r for r in exact["by_episode"]}
    assert len(exact_rows)==expected_assignments
    if exact_path != EXPORT/"exact_usage.json":
        shutil.copy2(exact_path,EXPORT/"exact_usage.json")
        shutil.copy2(exact_csv,EXPORT/"episode_calls.csv")
archive=EXPORT/"execution_evidence.zip"
with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=7) as out:
    out.write(RUNS/"eval_summary.csv","eval_summary.csv")
    for t in ids:
        for method in METHODS:
            for seed in protocol["planned_seeds"]:
                sd=RUNS/"python"/t/method/f"seed{seed}"
                tp=sd/f"{t}.traj.json"
                tr=load(tp);result=load(sd/"result.json");check=load(sd/"eval_report.json")["items"][0]
                assert result["method"]==method and result["seed"]==seed and result["instance_id"]==t
                info=tr["info"]; status=info["exit_status"]; patch=info["submission"] or ""
                assert status in {"Submitted","LimitsExceeded"}
                calls,in_tok,out_tok,longest=consumption(tr)
                assert calls<=info["model_stats"]["api_calls"]<=protocol["step_limit"]
                assert longest<=protocol["max_new_tokens_per_call"]
                row=evaluated[sd.resolve()]
                resolved=row["resolved"].lower() in {"true","1"}
                assert resolved==(check.get("passed_match",False) and not bool(check.get("error")))
                memory_text=sd/"retrieved_experiences.txt"
                injection=memory_text.read_text(encoding="utf8").strip() if memory_text.exists() else ""
                if method=="base": assert not injection
                elif protocol["runs_subdir"]=="pilot_in_loop":assert not injection
                else: assert injection
                stat={"target":t,"method":method,"seed":seed,"exit_status":status,"patch_bytes":len(patch.encode()),
                    "agent_calls":info["model_stats"]["api_calls"],"calls_with_usage":calls,"input_tokens":in_tok,"output_tokens":out_tok,
                    "max_output_tokens_one_call":longest,"duration_s":result["duration_s"],"injection_words":len(injection.split()),
                    "injection_bytes":len(injection.encode()),"resolved":resolved,"F2P_expected":expected_tests[t][0],
                    "P2P_expected":expected_tests[t][1],"F2P_passed":len(check["from_fail_to_pass"]) if "from_fail_to_pass" in check and not check.get("error") else None,
                    "P2P_lost":len(check["failed_from_pass_to_pass"]) if "failed_from_pass_to_pass" in check and not check.get("error") else None,
                    "checker_error":check.get("error",""),"test_executed":bool(check.get("log_path")),
                    "trajectory_sha256":sha(tp),"report_sha256":sha(sd/"eval_report.json"),
                    "submission_sha256":hashlib.sha256(patch.encode()).hexdigest() if patch else None}
                changed_paths = sorted({dst for _,dst in re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$",patch)})
                stat["submitted_diff_paths"]=changed_paths
                stat["submitted_test_paths"]=[q for q in changed_paths if q.startswith(("test/","tests/")) or "/tests/" in q]
                stat["native_input_tokens"]=in_tok
                stat["native_output_tokens"]=out_tok
                charge=exact_rows.get((t,method,seed))
                if charge:
                    assert charge["calls"]==stat["agent_calls"]
                    stat.update(input_tokens=charge["prompt_tokens"],output_tokens=charge["completion_tokens"],format_errors=charge["format_errors"],calls_accounted=charge["calls"])
                else:
                    stat["calls_accounted"]=calls
                rows.append(stat)
                for name in [tp.name,"result.json","run.log","eval_report.json","eval_stdout.log","eval_stderr.log","retrieved_experiences.txt"]:
                    f=sd/name
                    if f.exists():out.write(f,str(f.relative_to(RUNS)))
                for f in (sd/"logs").glob("*"):
                    if f.is_file():out.write(f,str(f.relative_to(RUNS)))
    interrupted=[]
    interroot=STORE/("interrupted" if EXPORT==HERE else protocol["runs_subdir"]+"_interrupted")
    for tp in sorted(interroot.rglob("*.traj.json")):
        tr=load(tp);info=tr["info"];calls,i,o,m=consumption(tr)
        parts=tp.relative_to(interroot).parts
        item={"target":parts[1],"method":parts[2],"seed":int(parts[3][4:]),"agent_calls":info["model_stats"]["api_calls"],
            "calls_with_usage":calls,"input_tokens":i,"output_tokens":o,"exit_status":info["exit_status"],"trajectory_sha256":sha(tp)}
        interrupted.append(item)
        for f in [tp,tp.parent/"run.log"]:
            out.write(f,"interrupted/"+str(f.relative_to(interroot)))
    for f in (STORE/"calibration").glob("*/*/report.json"):
        out.write(f,"calibration/"+str(f.relative_to(STORE/"calibration")))
        for log in (f.parent/"logs").glob("*"):
            out.write(log,"calibration/"+str(log.relative_to(STORE/"calibration")))
with (EXPORT/"attempts.jsonl").open("w",encoding="utf8") as f:
    for row in rows:f.write(json.dumps(row,ensure_ascii=False)+"\n")
by_method={}
for method in METHODS:
    rr=[x for x in rows if x["method"]==method]
    by_method[method]={"episodes":len(rr),"resolved":sum(int(x["resolved"]) for x in rr),
        "submitted":sum(x["exit_status"]=="Submitted" for x in rr),"nonempty_patches":sum(bool(x["patch_bytes"]) for x in rr),
        "tests_executed":sum(x["test_executed"] for x in rr),
        "per_target":{t:[int(x["resolved"]) for x in rr if x["target"]==t] for t in ids},
        "totals":{k:round(sum(x[k] for x in rr),1) for k in ["agent_calls","calls_with_usage","calls_accounted","input_tokens","output_tokens","duration_s"]}}
summary={"design":f"2 purposively chosen targets x {len(protocol['planned_seeds'])} paired seeds x {len(METHODS)} methods", "solver":protocol["solver"],"unrun":[{"target":t,"method":m,"seed":s,"reason":"administrative pre-outcome reallocation"} for t in ids for m in METHODS for s in (set(COHORT["planned_seeds"])-set(protocol["planned_seeds"]) if EXPORT==HERE else set())],"by_method":by_method,
    "interrupted":interrupted,"interruption_reason":("Host restart. Partial attempts archived; cells restarted in fresh verified containers from their same seed. First target/seed 0 batched across four arms; remaining cells run one at a time." if EXPORT==HERE else "Every cell runs sequentially."),
    "graded_attempts":len(rows),"evidence_sha256":sha(archive)}
interruption_log=EXPORT/"interruption_accounting.json"
if interruption_log.is_file():
    interrupted_usage=load(interruption_log)
    summary["interruption_reason"]=interrupted_usage["windows_stop"]
    summary["incomplete_attempt_native_cost"]={
        k:interrupted_usage[k] for k in ("seen_interrupted_native_calls","input_tokens","output_tokens","partial_trajectory_sha256")
    }
(EXPORT/"results.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
print(json.dumps(by_method))
