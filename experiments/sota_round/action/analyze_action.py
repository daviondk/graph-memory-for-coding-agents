"""Summarize every assigned cell, without conditioning on parse or execution success."""
import argparse
import collections
import csv
import json
import math
import random
import statistics
from pathlib import Path


def lines(path):
    return [json.loads(s) for s in path.read_text("utf-8").splitlines() if s.strip()]


def estimate(rows,left,right):
    diff=[int(r[left])-int(r[right]) for r in rows]
    n=len(diff)
    wins=diff.count(1)
    losses=diff.count(-1)
    disc=wins+losses
    p=min(1.0,2*sum(math.comb(disc,j) for j in range(min(wins,losses)+1))/2**disc) if disc else 1.0
    rng=random.Random(20261116)
    boot=sorted(sum(rng.choices(diff,k=n))/n for _ in range(20_000))
    return dict(n=n,wins=wins,losses=losses,ties=n-disc,delta=sum(diff)/n,
                paired_percentile_ci95=[boot[499],boot[19499]],exact_two_sided_mcnemar=p,
                fixed=[r["task"] for r in rows if r[left] and not r[right]],
                harmed=[r["task"] for r in rows if r[right] and not r[left]])


def summary(data):
    return dict(total=sum(data), mean=statistics.mean(data), median=statistics.median(data),
                min=min(data),max=max(data)) if data else None


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--study",type=Path,default=Path(__file__).resolve().parent)
    cli.add_argument("--repo",type=Path,required=True)
    args=cli.parse_args()
    root=args.study
    assigned=lines(root/"assigned.jsonl")
    n=102
    grades={r["id"]:r for r in lines(root/"graded.jsonl")}
    assert len(assigned)==len(grades)==n
    assert {r["id"] for r in assigned} == set(grades)
    refs=lines(root/"canaries.jsonl")
    assert len(refs)==103 and all(r["ok"]==(r["arm"] in ("informed","isolation")) and not r.get("infrastructure") for r in refs)
    task_rows={}
    cell_rows=[]
    arms=("raw","receipt","empty")
    for j in assigned:
        key=j["id"]
        gr=grades[key]
        has_log=(root/"logs"/(key+".json")).is_file()
        log=json.loads((root/"logs"/(key+".json")).read_text("utf-8")) if has_log else {}
        if has_log:
            assert log["id"]==key and gr["task"]==j["task"] and gr["arm"]==j["arm"]
        usage=log.get("usage",{})
        try:
            body=json.loads(log.get("text",""))["builder"]
        except (KeyError,TypeError,json.JSONDecodeError):
            body=None
        checker=gr.get("checker",{})
        builder=gr.get("builder",{})
        t=task_rows.setdefault(j["task"],dict(task=j["task"],family=j["task"].split("-",1)[0],
                                              kind=json.loads((args.repo/"tasks"/j["task"]/"task.json").read_text("utf-8"))["kind"]))
        t[j["arm"]]=bool(gr.get("ok",False))
        if j["arm"] in ("receipt","raw"):
            sources=list(j["sources"])
            assert len(sources)==2 and len(set(sources))==2 and j["memory_words"]<=300
            assert sources==t.get("sources",sources)
            t["sources"]=sources
            prec=args.repo/"tasks"/j["task"]/"precursors"
            need={f"sessions/{j['task']}/{x.name}.jsonl" for x in prec.iterdir() if x.is_dir()} if prec.is_dir() else set()
            t["expected_precursor_sessions"]=len(need)
            t["retrieved_precursors"]=len(set(sources)&need)
            t["all_precursors_fetched"]=bool(need) and need.issubset(sources)
        cell_rows.append(dict(id=key,task=j["task"],arm=j["arm"],ok=bool(gr.get("ok",False)),
                              response_state=gr["response_state"],builder_state=builder.get("state"),
                              echoed_placeholder=isinstance(body,str) and body.strip()=="complete Python 3 source",
                              syntax_error="SyntaxError:" in builder.get("stderr",{}).get("tail",""),
                              builder_returncode=builder.get("returncode"),checker_state=checker.get("state"),
                              infrastructure=gr.get("infrastructure",False),verdict=gr.get("verdict","missing model output"),
                              initial_tree_sha256=gr.get("initial_tree_sha256"),memory_words=j["memory_words"],
                              input_tokens=usage.get("input_tokens"),output_tokens=usage.get("output_tokens"),
                              at_limit=log.get("at_limit"),batch=log.get("batch"),batch_seconds=log.get("batch_seconds"),
                              builder_seconds=builder.get("seconds"),checker_seconds=checker.get("seconds")))
    task_rows=sorted(task_rows.values(),key=lambda r:r["task"])
    assert len(task_rows)==34 and all(set(arms).issubset(t) for t in task_rows)
    for t in task_rows:
        hashes={r["initial_tree_sha256"] for r in cell_rows if r["task"]==t["task"] and r["initial_tree_sha256"]}
        assert len(hashes)<=1
    for name,rows in [("action_per_task.csv",task_rows),("action_per_cell.csv",cell_rows)]:
        with (root/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    comparisons={f"{left}_minus_{right}":estimate(task_rows,left,right)
                 for left,right in (("receipt","raw"),("receipt","empty"),("raw","empty"))}
    without=[t for t in task_rows if t["task"]!="ts-bool-env"]
    splits={"excluding_ts_bool_env":without}
    for family in ("ts","xs","fa"):
        splits[family]=[t for t in task_rows if t["family"]==family]
    for flag in (True,False):
        splits[f"all_precursors_fetched_{flag}"]=[t for t in task_rows if t["all_precursors_fetched"]==flag]
    strata={k:dict(n=len(v),**{a:sum(t[a] for t in v) for a in arms}) for k,v in splits.items() if v}
    by_arm={}
    for arm in arms:
        group=[r for r in cell_rows if r["arm"]==arm]
        by_arm[arm]=dict(n=len(group), successes=sum(r["ok"] for r in group),
                         response_counts=dict(collections.Counter(r["response_state"] for r in group)),
                         builder_counts=dict(collections.Counter(r["builder_state"] for r in group)),
                         checker_counts=dict(collections.Counter(r["checker_state"] for r in group)),
                         infrastructure=sum(r["infrastructure"] for r in group),
                         at_output_limit=sum(bool(r["at_limit"]) for r in group),
                         echoed_placeholder=sum(r["echoed_placeholder"] for r in group),
                         syntax_errors=sum(r["syntax_error"] for r in group),
                         crashed_but_passed=[r["task"] for r in group if r["builder_state"]=="nonzero" and r["ok"]],
                         **{k:summary([r[k] for r in group if r[k] is not None]) for k in
                            ("input_tokens","output_tokens","memory_words","builder_seconds","checker_seconds")})
    batches={r["batch"]:r["batch_seconds"] for r in cell_rows if r["batch"] is not None}
    result=dict(n_tasks=34,n_assigned=102,all_cells_included=True,arms=by_arm,paired=comparisons,
                sensitivity_without_bool=estimate(without,"receipt","raw"),strata=strata,
                canaries=dict(informed=34,naive_failed=34,noop_failed=34,isolation_pass=True),
                whole_batch_generation_seconds=summary(list(batches.values())))
    raw_tokens=by_arm["raw"]["input_tokens"]["total"]
    receipt_tokens=by_arm["receipt"]["input_tokens"]["total"]
    empty_tokens=by_arm["empty"]["input_tokens"]["total"]
    result["prompt_cost"]=dict(raw_tokens=raw_tokens,receipt_tokens=receipt_tokens,empty_tokens=empty_tokens,
                               fewer_tokens=raw_tokens-receipt_tokens,relative_to_full_raw=(raw_tokens-receipt_tokens)/raw_tokens,
                               relative_to_raw_increment=(raw_tokens-receipt_tokens)/(raw_tokens-empty_tokens))
    (root/"action_results.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(arms={a:v["successes"] for a,v in by_arm.items()},primary=comparisons["receipt_minus_raw"]),indent=2))


if __name__=="__main__":
    main()
