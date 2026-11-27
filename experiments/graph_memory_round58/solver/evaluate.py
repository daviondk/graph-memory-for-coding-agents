"""Grade only sealed answers. The separate grader may access head doctests."""
import ast
from collections import Counter
import itertools
import json
import math
import random
import statistics
import importlib.util
from solve import HERE, OLD, ARMS, common, grade, isolation, study, save, read
audit_spec=importlib.util.spec_from_file_location("historical_input_audit",OLD/"audit.py")
audit=importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit)

LABELS = ("draft",) + ARMS


def ast_calls(s, name):
    try:
        tree = ast.parse(s)
    except (SyntaxError, ValueError):
        return set()
    values = set()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if ((isinstance(fn, ast.Name) and fn.id == name) or
            (isinstance(fn, ast.Attribute) and fn.attr == name)):
            values.add(ast.dump(ast.Call(func=ast.Name(id=name,ctx=ast.Load()),args=call.args,keywords=call.keywords)))
    return values


def summary(rows):
    return {k:dict(all_pass=sum(r[k]["passed"] for r in rows),n=len(rows),
                   passed_examples=sum(r[k]["good"] for r in rows),
                   examples=sum(r[k]["total"] for r in rows),
                   macro_example_fraction=statistics.fmean(r[k]["good"]/r[k]["total"] for r in rows))
            for k in LABELS} if rows else {}


def paired(records,plan,arm,base):
    diffs = [int(r[arm]["passed"])-int(r[base]["passed"]) for r in records.values()]
    by_repo = [sum(d for d,q in zip(diffs,records) if q.startswith(repo+"|")) for repo in study.SPECS]
    rng = random.Random(580412)
    bootstrap=sorted(sum(rng.choices(diffs,k=len(diffs)))/len(diffs) for _ in range(20000))
    obs=abs(sum(by_repo))
    p=statistics.fmean(abs(sum(a*b for a,b in zip(by_repo,mask)))>=obs for mask in itertools.product((-1,1),repeat=len(by_repo)))
    address_diff=sum(plan[q]["arms"][arm]["index"]!=plan[q]["arms"][base]["index"] for q in records) if base!="draft" else None
    diff_outputs=sum(r[arm]["code_key"]!=r[base]["code_key"] for r in records.values())
    distinct=sum(r[arm]["hash"]!=r[base]["hash"] for r in records.values())
    return dict(wins=diffs.count(1),losses=diffs.count(-1),ties=diffs.count(0),
                delta_pp=100*sum(diffs)/len(diffs),bootstrap_task_CI95_pp=[100*bootstrap[499],100*bootstrap[19499]],
                repo_signflip_p=p,repo_sums=by_repo,different_inputs=distinct,different_selected_index=address_diff,
                condition_specific_ceiling_pp=100*distinct/len(diffs),different_implementations=diff_outputs)


def main():
    assert all(common.sha(HERE/n)==h for n,h in read("answer-seal.json").items())
    assert all(common.sha(HERE/n)==h for n,h in read("generation-seal.json")["hashes"].items())
    selection=read("selection.json.gz");plan=read("assignments.json.gz");answers=read("answers.json.gz")
    cal=read("calibration.json.gz");inp=read("inputs.json.gz");design=read("draft-design.json.gz")
    assert set(inp)==set(answers)
    jobs={};by_question={};keep=Counter()
    for q,row in plan.items():
        t=selection[q]["task"]; refs={"draft":row["draft"],**{a:b["hash"] for a,b in row["arms"].items()}}
        by_question[q]={}
        for arm,h in refs.items():
            raw=answers[h]["text"]
            kept=arm!="draft" and raw.strip()=="KEEP"
            if kept:
                keep[arm]+=1
                raw=answers[row["draft"]]["text"]
            code,status=grade.parse_answer(raw,t["name"])
            key=study.digest((code or raw).encode())
            by_question[q][arm]=dict(hash=h,code_key=key,parse=status,keep=kept)
            if code:
                i=q+"|"+key
                jobs[i]=dict(id=i,repo=t["repo"],path=t["path"],name=t["name"],kind="model",answer=code)
    measured=isolation.execute(list(jobs.values()))
    save("execution.json.gz",measured)
    for q,rows in by_question.items():
        n=cal[q+"|reference"]["run"]
        for arm,item in rows.items():
            v=measured.get(q+"|"+item["code_key"],{})
            good=n-v["failed"] if v.get("run")==n else 0
            item.update(passed=good==n,good=good,total=n,executed=v.get("run")==n)
    save("records.json.gz",by_question)
    gold=json.loads((study.RAW/"author-inputs.json").read_bytes())
    overlap={}
    first={}
    visible=read("draft-visible.json.gz")
    for q,r in plan.items():
        name=selection[q]["task"]["name"]
        calls=set().union(*(ast_calls(s,name) for s in gold[q]["examples"]))
        overlap[q]=[bool(ast_calls(c["expr"],name)&calls) for c in design["checks"][q]]
        history_tokens=audit.norm_tokens(visible[q].split("\n",1)[-1])
        first[q]=any(audit.fmatched(audit.norm_tokens(call),history_tokens) for example in gold[q]["examples"]
                     for call in audit.target_calls(example,name))
    save("overlap.json",dict(probes=overlap,first_excerpt=first))
    results=dict(tasks=len(plan), eligible_before_calibration=len(read("selection-seal.json")["candidates"]),
                 n_graded_implementations=len(measured),arms=summary(list(by_question.values())),
                 by_repo={p:summary([r for q,r in by_question.items() if q.startswith(p+"|")]) for p in study.SPECS},
                 paired={a+"_vs_"+b:paired(by_question,plan,a,b) for a,b in
                         [("adaptive","static"),("adaptive","masked"),("adaptive","review"),("static","review"),
                          ("adaptive","draft"),("review","draft")]},
                 checked_input_overlap_any=sum(any(vals) for vals in overlap.values()),
                 overlap_any_count=sum(sum(v) for v in overlap.values()),
                 selected_overlap={a:sum(v[plan[q]["arms"][a]["index"]] for q,v in overlap.items())
                                   for a in ("static","adaptive")},
                 any_probe_overlap_excluded=summary([r for q,r in by_question.items() if not any(overlap[q])]),
                 first_excerpt_overlap=sum(first.values()),
                 first_and_probe_overlap_excluded=summary([r for q,r in by_question.items() if not first[q] and not any(overlap[q])]),
                 implemented_keep=dict(keep),status=dict(Counter(v for r in plan.values() for v in r["status"])),
                 failed_probe_tasks=sum("FAIL" in v["status"] for v in plan.values()),
                 actual_probe_outputs=sum(len(a.get("values",[])) for a in read("probe-execution.json.gz").values()),
                 computed_cost={kind:dict(unique=len(hs),input_tokens=sum(len(inp[h]) for h in hs),
                                           output_tokens=sum(answers[h]["tokens"] for h in hs),
                                           output_truncations=sum(answers[h]["stop"]=="limit" for h in hs)) for kind,hs in
                                (("drafts",set(design["assign"].values())),("revisions",set(inp)-set(design["assign"].values())))},
                 virtual_per_arm={a:dict(input_tokens=sum(len(inp[r["arms"][a]["hash"]]) for r in plan.values()),
                                         output_tokens=sum(answers[r["arms"][a]["hash"]]["tokens"] for r in plan.values()))
                                  for a in ARMS})
    save("results.json",results)
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
