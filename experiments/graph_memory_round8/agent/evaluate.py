"""Post-seal evaluation of paired interactive choices and executable patches."""
import concurrent.futures
import importlib.util
import math
import shutil
import sys
import tarfile
from collections import Counter
import harness as h

D = h.D

def grader():
    spec = importlib.util.spec_from_file_location("previous_grade", h.OLD/"grade.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.D = D
    return mod

def answers():
    ids = h.check()
    lock = h.read(D/"answer_lock.json")
    assert h.filehash(D/"input_lock.json") == lock["input"]
    assert all(h.filehash(D/rel) == sha for rel,sha in lock["files"].items())
    return ids

def grade():
    ids = answers()
    evaluator = grader()
    for i in ids:
        shutil.copyfile(h.OLD/"tasks"/i/"grading.json", D/"tasks"/i/"grading.json")
    for phase in ("control", "solver"):
        jobs = [(i,phase) for i in ids if not (D/"tasks"/i/"grades_v2"/(phase+".json")).is_file()]
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            list(pool.map(evaluator.task, jobs))

def cost(keys):
    c=Counter()
    for key in keys:
        x=h.read(D/"calls"/(key+".json.gz"))
        assert h.sh(h.canonical(x["request"]))==key
        usage=x["response"]["usage"]
        c.update(calls=1,prompt_tokens=usage["prompt_tokens"],answer_tokens=usage["completion_tokens"],
                 model_wall_s=sum(a["elapsed"] for a in x["attempts"]),attempts=len(x["attempts"]))
    return dict(c)

def paired(rows, metric):
    changes=[int(r["pointer"][metric])-int(r["history"][metric]) for r in rows]
    w,l=changes.count(1),changes.count(-1)
    n=w+l
    p=min(1,2*sum(math.comb(n,k) for k in range(min(w,l)+1))/2**n) if n else 1
    return dict(n_tasks=len(rows),pointer_wins=w,history_wins=l,ties=len(rows)-n,delta_tasks=w-l,exact_two_sided_p=p)

def report():
    ids=answers()
    rows=[]; armkeys={x:[] for x in h.METHODS.values()}; actions={}
    for i in ids:
        task=D/"tasks"/i
        ctrl=h.read(task/"grades_v2/control.json")
        grades=h.read(task/"grades_v2/solver.json")
        groups=["FAIL_TO_PASS","PASS_TO_PASS"]
        b,g=(ctrl[k]["tests"] for k in ("base","gold"))
        green=set(b[groups[1]]["passed"])
        both_complete=all(d[k]["complete"] for d in (b,g) for k in groups)
        valid=(both_complete and bool(b[groups[0]]["failed"]) and not g[groups[0]]["failed"]
               and green <= set(g[groups[1]]["passed"]))
        r={"task":i,"control_valid":valid,"controls_complete":both_complete,"base_failing":len(b[groups[0]]["failed"]),
           "target_tests":len(b[groups[0]]["requested"]),"base_green_regression":len(green),
           "reference_lines":ctrl["gold"]["gold_lines"]}
        for method,arm in h.METHODS.items():
            t=h.read(task/(method+".json.gz")); ev=t["events"]; item=grades[method]; tests=item["tests"]
            ft,pt=(tests[k] for k in groups)
            r["initial_query"]=t["shared"]["query"]
            r["initial_matches"]=len(t["shared"]["history"])
            keys=t["keys"]; armkeys[arm].extend(keys)
            armcost=cost(keys); armcost["tool_wall_s"]=t["tool_seconds"]
            armcost["full_wall_s"]=armcost["model_wall_s"]+armcost["tool_wall_s"]
            spans=[e["span"] for e in ev if e.get("span")]
            located=any(any(s["start"]<=n<=s["end"] for n in r["reference_lines"].get(s["path"],[]))
                        for s in spans if not s["truncated"])
            seq=[(e["type"], e.get("span",{}),e["decision"].get("search")) for e in ev]
            actions[i,arm]=seq
            outcome=bool(item["applied"] and ft["complete"] and pt["complete"] and not ft["failed"] and green<=set(pt["passed"]))
            r[arm]=dict(strict_success=outcome,applied=item["applied"],reason=item["reason"],target_passed=len(ft["passed"]),
                        regression_green_lost=sorted(green-set(pt["passed"])),complete=ft["complete"] and pt["complete"],
                        final_key=t["final"],actions=seq,localized=located,exposures=sum(bool(e["ptr_before"]) for e in ev),
                        exact_address_reads=sum(bool(e.get("matched")) for e in ev),valid_reads=len(spans),
                        truncated_reads=sum(bool(s["truncated"]) for s in spans),cost=armcost)
        r["different_actions"]=actions[i,"history"]!=actions[i,"pointer"]
        r["different_final_prompt"]=r["history"]["final_key"]!=r["pointer"]["final_key"]
        rows.append(r)
    valid=[r for r in rows if r["control_valid"] and all(r[a]["complete"] for a in armkeys)]
    results={"tasks":len(rows),"valid_and_complete":len(valid),"changed_trajectories":sum(r["different_actions"] for r in rows),
             "changed_final_prompts":sum(r["different_final_prompt"] for r in rows),"initial_search_nonempty":sum(bool(r["initial_matches"]) for r in rows),
             "primary":paired(valid,"strict_success"),"localization":paired(rows,"localized"),"applications":paired(rows,"applied")}
    for arm,keys in armkeys.items():
        c=cost(keys)
        c["tool_wall_s"]=sum(r[arm]["cost"]["tool_wall_s"] for r in rows)
        c["full_wall_s"]=c["model_wall_s"]+c["tool_wall_s"]
        results[arm]={k:sum(r[arm][k] for r in rows) for k in ("applied","exposures","exact_address_reads","valid_reads","localized","truncated_reads")}
        results[arm].update(strict_success=sum(r[arm]["strict_success"] for r in valid),cost=c)
    results["physical_unique_model"]=cost(sorted(set().union(*map(set,armkeys.values()))))
    results["source"]="Historical SWE-bench Verified SymPy, sampled regressions, native Windows pytest"
    h.write(D/"rows.json",rows);h.write(D/"results.json",results)
    return results

def verify():
    ids=answers();mod=grader();checked=0
    for i in ids:
        task=D/"tasks"/i;g=h.read(task/"grading.json");cfg=h.read(task/"public_input.json.gz")
        src=h.OLD/"tasks"/i
        assert h.filehash(task/"grading.json")==h.filehash(src/"grading.json")
        archive=src/"checkout.tar.gz"
        assert h.filehash(archive)==cfg["checkout"]["sha256"]
        selected=set(cfg["paths"])|mod.paths(g["patch"])|mod.paths(g["test_patch"])
        with tarfile.open(archive) as z:
            members={m.name.partition("/")[2]:m for m in z if m.isfile() and "/" in m.name}
            for s in selected:
                path=task/"base"/s
                if s in members:
                    assert path.read_bytes()==z.extractfile(members[s]).read(),(i,s)
                else:assert not path.exists(),(i,s)
                checked+=1
    outputs=[D/"rows.json",D/"results.json"];orig=[h.filehash(p) for p in outputs]
    report()
    assert orig==[h.filehash(p) for p in outputs]
    h.write(D/"verification.json",dict(tasks=len(ids),restored_files=checked,archive_hashes=True,results_sha256=orig[1],rows_sha256=orig[0],
                                       locked_files=len(h.read(D/"answer_lock.json")["files"])))
if __name__=="__main__":
    {"grade":grade,"report":report,"verify":verify}[sys.argv[1]]()
