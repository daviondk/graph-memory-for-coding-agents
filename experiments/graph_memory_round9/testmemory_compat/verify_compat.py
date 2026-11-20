"""Independently verify the paired denominator, unchanged public inputs and movement across two interpreters."""
import importlib.metadata as md
import json
import os
import sys
from collections import Counter
from pathlib import Path
from collect import ROOT,AGENT,read,save,digest
from predict import unpack,status
def main():
    current=read(ROOT/"outcomes.json"); result=read(ROOT/"results.json"); ver=read(ROOT/"verification.json")
    oldroot=ROOT.parent/"testmemory";legacy=read(oldroot/"verification.json")
    key=lambda r:(r["task"],r["direction"],r["node"])
    ol={key(r):r for r in legacy};now={key(r):r for r in ver}
    assert set(ol)==set(now)=={key(r) for r in current} and len(now)==212 and all(r["eligible"] for r in ver)
    ids=read(ROOT/"collection-inputs.json")["ids"];assert len(ids)==10
    before=read(oldroot/"collection-inputs.json");after=read(ROOT/"collection-inputs.json");assert before["sources"]==after["sources"]
    for i in ids:
        p=ROOT/"runs"/i
        assert read(p/"nodes.json")==read(oldroot/"runs"/i/"nodes.json")
        for state,sha in read(p/"testmon-lock.json").items():assert digest((p/("testmon-"+state+".json")).read_bytes())==sha
    for k,s in read(ROOT/"prediction-lock.json").items():assert digest((ROOT/k).read_bytes())==s
    recovered=[{"task":r["task"],"direction":r["direction"],"node":r["node"],"current":[r["prior"],r["current"]],"old":[ol[key(r)]["prior"],ol[key(r)]["current"]]} for r in ver if not ol[key(r)]["eligible"]]
    scope_covered={}; fliplists={}
    for direction in ["fix","revert"]:
        group=[r for r in current if r["direction"]==direction];assert len(group)==106
        flips=[r for r in group if r["changed"]];fliplists[direction]=[]
        for r in flips:
            fliplists[direction].append({k:r[k] for k in ["task","node","old_affected","prior","actual"]}|{"testmon":r["selected"]["testmon"],"exact_scope":r["selected"]["symbol"]})
        files_only=[r for r in group if r["selected"]["file"] and not r["selected"]["symbol"]]
        scope_covered[direction]=dict(file_candidate_but_unchanged_scope=len(files_only),flips_on_them=sum(r["changed"] for r in files_only),
            no_scope_dependency=sum(not r["selected"]["symbol"] for r in group),flips_without_dependency=sum(r["changed"] and not r["selected"]["symbol"] for r in group),
            all_reached_changed_scopes=sum(r["selected"]["symbol"] for r in group))
    a=ROOT/"immutable_audit_final"
    ctrl={d["mode"]:d for d in read(a/"results.json")}
    assert set(ctrl)=={"single_revert","single_fix","reverse_order_revert","edited_test","touch_only"}
    assert all(x["mtime_after"]-x["mtime_before"]==200 for x in ctrl.values())
    for m in ["single_revert","reverse_order_revert"]:
        assert ctrl[m]["plugin_after"] is None and ctrl[m]["direct_pytest_after"]==1
        assert not read(a/m/"details.json")["tracked_fingerprints_for_target"]
    assert ctrl["single_fix"]["plugin_after"] and ctrl["single_fix"]["direct_pytest_after"]==0
    assert ctrl["edited_test"]["plugin_after"] and ctrl["edited_test"]["direct_pytest_after"]==1
    assert ctrl["touch_only"]["plugin_after"] is None and ctrl["touch_only"]["direct_pytest_after"]==0
    versions={p:md.version(p) for p in ["coverage","pytest","mpmath","pytest-testmon","py"]}
    assert versions=={"coverage":"7.13.5","pytest":"7.4.4","mpmath":"1.2.1","pytest-testmon":"2.3.1","py":"1.11.0"} and sys.version_info[:3]==(3,11,15)
    data=dict(python=sys.version,versions=versions,freeze_sha256=digest((ROOT/"runtime-freeze.txt").read_bytes()),all_groups_106=True,valid_total=len(now),directions=2,
        selected_leakage="prediction sealed before scoring; outcome reproduction uses native tests",recovered=recovered,scope_covered=scope_covered,flips=fliplists,
        plugin_code_same=read(ROOT/"testmon-input.json")["package_files"]==read(oldroot/"testmon-input.json")["package_files"],result_sha256=digest((ROOT/"results.json").read_bytes()),independent_scenarios=sorted(ctrl))
    assert data["plugin_code_same"]
    save(ROOT/"compatibility-verification.json",data);print(data["valid_total"],len(recovered),scope_covered)
if __name__=="__main__":main()
