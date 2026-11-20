"""Offline replay of handoff assignment, prompt controls, seeds, model usage, snapshots and grades."""
from pathlib import Path
import math
from handoff import ROOT, SYSTEM, TOOL, items, payload, read, sha
from analysis import field_stats, exact_p

def verify():
    roster=read(ROOT/"assignments.json")
    assert len(roster)==len({tuple(v) for v in roster})==8
    assert roster==sorted(roster,key=lambda v:sha(("continuation-order-v1|"+"|".join(v)).encode()))
    for fname in ("design_lock.json","implementation_lock.json"):
        for n,h in read(ROOT/fname)["sha256"].items():assert sha((ROOT/n).read_bytes())==h
    for n,h in read(ROOT/"end_lock.json")["files"].items():assert sha((ROOT/n).read_bytes())==h,n
    summary=read(ROOT/"results.json")
    paired={}
    for iid,arm in roster:
        h=ROOT/"handoffs"/iid; d=ROOT/"runs"/iid/arm;input_lock=read(h/"input_lock.json")
        for n,hsh in input_lock["files"].items():assert sha((h/n).read_bytes())==hsh
        prev=items(h/"previous_actions.jsonl");patch=(h/"inherited.patch").read_bytes()
        tail,ledger=payload(prev,patch)
        common=(h/"common_user.txt").read_bytes().decode("utf-8")
        extra=(h/"manifest_only.txt").read_bytes().decode("utf-8")
        assert common.endswith("\n"+tail) and extra=="\n\nAction log from the previous session:\n"+ledger
        first=read(d/"prompt-01.json")
        assert first["messages"]==[{"role":"system","content":SYSTEM},{"role":"user","content":common+(extra if arm=="manifest" else "")}]
        c=read(d/"complete.json")
        assert 1<=c["calls"]<=8 and c["initial_tree_sha256"]==sha(patch)
        tokens=[0,0];actionlog=[]
        for t in range(c["calls"]):
            p=read(d/f"prompt-{t+1:02}.json"); r=read(d/f"response-{t+1:02}.json")
            assert p["temperature"]==.5 and p["top_p"]==.95 and p["max_tokens"]==768 and p["tools"]==[TOOL] and p["model"]=="qwen38-27b-ud-q4km"
            assert p["seed"]==int(sha(("continuation-v1|"+iid+"|"+str(t)).encode())[:8],16)%(2**31-1)
            assert p["messages"][:2]==first["messages"]
            tokens=[tokens[0]+r["usage"]["prompt_tokens"],tokens[1]+r["usage"]["completion_tokens"]]
            actionlog.extend(read(d/f"actions-{t+1:02}.json"))
        assert actionlog==items(d/"actions.jsonl")
        assert tokens==[c["input_tokens"],c["output_tokens"]]
        result=read(ROOT/"grading"/"receipts"/iid/(arm+".json"))
        assert result["input_patch_sha256"]==c["patch_sha256"]==sha((d/"candidate.patch").read_bytes()) and result["official_exit"]==0
        paired[iid,arm]=result["resolved"]
        parent=read(ROOT/"grading"/"parents"/(iid+".json"));assert parent["input_patch_sha256"]==sha(patch)
        published=next(v for v in summary["pairs"] if v["target"]==iid)
        assert published["baseline_solved"]==parent["resolved"] and published[arm+"_solved"]==result["resolved"]
    wins=sum(paired[i,"manifest"] and not paired[i,"last_two"] for i,a in roster if a=="manifest")
    losses=sum(paired[i,"last_two"] and not paired[i,"manifest"] for i,a in roster if a=="manifest")
    assert summary["wins"]==wins and summary["losses"]==losses and math.isclose(summary["p_exact_descriptive"],exact_p(wins,losses))
    print("OK: 8 frozen handoffs, sole first-prompt difference, exact tree hashes, model seeds, usage and official paired grades")

if __name__=="__main__":verify()

