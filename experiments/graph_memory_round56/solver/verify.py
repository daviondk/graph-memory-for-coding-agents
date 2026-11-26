"""Recompute selection receipts, assignment metrics and prefix ancestry from primitive records."""
from collections import Counter
import argparse
import math
import struct
from study import *

def main():
    opts=argparse.ArgumentParser();opts.add_argument("--git",action="store_true");args=opts.parse_args()
    for k in ("selection-seal.json","witness-seal.json"):
        seal=read(k);h=seal.get("hashes",seal);assert all(digest((HERE/n).read_bytes())==v for n,v in h.items())
    sel=read("selections.json.gz");history=read("history.json.gz");checks=0
    for repo,h in history.items():
        sha=SPECS[repo][0]
        if args.git:
            full=git(repo,"rev-list","-n","194","--first-parent",sha).decode().splitlines()
            assert h["commits"]==full[1:-1][::-1] and h["boundary"]==full[-1]
            checks+=len(h["commits"])
        for e in h["episodes"]:assert h["commits"][e["i"]]==e["sha"] and e["anchors"]==h["files_touched"][e["i"]]
    for prefix in ("","extra-"):
        prompts,assigned,answers,records,results=(read(prefix+f) for f in
            ("prompts.json.gz","assignments.json.gz","answers.json.gz","records.json.gz","results.json"))
        assert set(answers)==set(prompts)
        for h,ids in prompts.items():assert digest(struct.pack(f"<{len(ids)}I",*ids))==h
        oracle=read("calibration.json.gz");measured=read(prefix+"execution.json.gz")["measured"]
        for q,arms in assigned.items():
            assert q in sel and len({x["tokens"] for x in arms.values() if x["evidence"]})==1
            for m,v in arms.items():
                assert len(prompts[v["hash"]])==v["tokens"]
                n=oracle[q+"|reference"]["run"];actual=measured.get(q+"|"+v["hash"],{})
                good=n-actual["failed"] if actual.get("run")==n else 0
                assert records[q][m]["good"]==good and records[q][m]["ok"]==(good==n)
        for m,total in results["summaries"].items():
            assert sum(v[m]["ok"] for v in records.values())==total["pass1"]
            assert sum(v[m]["good"] for v in records.values())==total["passed_examples"]
    choices=read("witness-decisions.json.gz");prev=read("records.json.gz");audit=read("audit.json")
    for mode in ("old_expected","consensus"):
        recovered=[prev[q][v[mode]] for q,v in choices.items()]
        assert audit["witness_all"][mode]==[sum(v["ok"] for v in recovered),len(recovered),sum(v["good"] for v in recovered),sum(v["total"] for v in recovered)]
    print("Verified both 36-task experiments, exact token budgets, historical probe decisions; first-parent transitions independently checked:",checks)
if __name__=="__main__":main()
