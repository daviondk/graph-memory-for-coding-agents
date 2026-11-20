"""Score blind sealed runs against official grader receipts; emit per-run costs and paired effects."""
from collections import Counter
import csv
import datetime
import math
from statistics import median

from handoff import ROOT, ev, is_test, items, normalize, read, sha, write_json

def field_stats(actions, previous):
    observed=[ev(a) for a in actions]
    old={normalize(ev(a)["cmd"]) for a in previous if ev(a)["executable"]}
    commands=[a for a in observed if a["executable"]]
    repeat=[a for a in commands if normalize(a["cmd"]) in old]
    return {"tool_calls":len(observed),"shell_commands":len(commands),"test_commands":sum(is_test(a["cmd"]) for a in commands),
            "previous_command_repeats":len(repeat),"previous_test_repeats":sum(is_test(a["cmd"]) for a in repeat),
            "shell_nonzero":sum(a["status"]!=0 for a in commands)}

def exact_p(w,l):
    n=w+l
    return min(1.,2*sum(math.comb(n,k) for k in range(min(w,l)+1))/2**n)

def analyze():
    assert (ROOT/"end_lock.json").exists()
    allruns=[]
    for iid,arm in read(ROOT/"assignments.json"):
        folder=ROOT/"runs"/iid/arm
        c=read(folder/"complete.json"); inherited=ROOT/"handoffs"/iid
        g=read(ROOT/"grading"/"receipts"/iid/(arm+".json"))
        parent=read(ROOT/"grading"/"parents"/(iid+".json"))
        assert sha((folder/"candidate.patch").read_bytes())==g["input_patch_sha256"]==c["patch_sha256"]
        assert sha((inherited/"inherited.patch").read_bytes())==parent["input_patch_sha256"]
        assert g["resolved"] in [True,False] and isinstance(g["resolved"],bool)
        assert isinstance(parent["resolved"],bool) and g["official_exit"]==0
        result={key:c[key] for key in ["id","arm","calls","input_tokens","output_tokens","elapsed_s","finish_reason","patch_bytes","patch_sha256","final_changed_vs_initial"]}
        result.update(field_stats(items(folder/"actions.jsonl"),items(inherited/"previous_actions.jsonl")))
        result.update(inherited_solved=parent["resolved"],solved=g["resolved"],patch_applied=g.get("patch_applied"),
                      official_evaluated_tests=g.get("tests_status_present"),official_summary_sha256=g["official_report_sha256"],
                      manifest_added_chars=len((inherited/"manifest_only.txt").read_bytes().decode("utf-8")) if arm=="manifest" else 0)
        allruns.append(result)
    assert len(allruns)==8
    with (ROOT/"per_run.csv").open("w",encoding="utf-8",newline="") as fp:
        w=csv.DictWriter(fp,fieldnames=list(allruns[0]));w.writeheader();w.writerows(allruns)
    stats={}
    for a in ("last_two","manifest"):
        rs=[r for r in allruns if r["arm"]==a]; assert len(rs)==4
        stats[a]={k:sum(r[k] for r in rs) for k in ["solved","calls","tool_calls","shell_commands","test_commands","previous_command_repeats",
                                                     "previous_test_repeats","shell_nonzero","input_tokens","output_tokens","elapsed_s","final_changed_vs_initial"]}
        stats[a].update(parent_already_solved=sum(r["inherited_solved"] for r in rs),
                        changed_from_fail_to_solved=sum(not r["inherited_solved"] and r["solved"] for r in rs),
                        regressions_from_solved=sum(r["inherited_solved"] and not r["solved"] for r in rs),
                        mean_extra_chars=sum(r["manifest_added_chars"] for r in rs)/len(rs))
    pairs=[]
    for iid in sorted({r["id"] for r in allruns}):
        x={r["arm"]:r for r in allruns if r["id"]==iid}; a=x["manifest"];b=x["last_two"]
        diffs={k:a[k]-b[k] for k in ["solved","previous_command_repeats","previous_test_repeats","test_commands","input_tokens","output_tokens","calls","elapsed_s"]}
        pairs.append({"target":iid,"baseline_solved":a["inherited_solved"],"last_two_solved":b["solved"],"manifest_solved":a["solved"],"delta":diffs})
    d=[q["delta"]["solved"] for q in pairs]; w=d.count(1);l=d.count(-1)
    result={"n":4,"arms":stats,"pairs":pairs,"wins":w,"losses":l,"ties":4-w-l,"difference_pp":100*sum(d)/4,"p_exact_descriptive":exact_p(w,l)}
    write_json(ROOT/"results.json",result)
    return result

if __name__=="__main__":
    analyze()

