"""Portable manifest and independent case-by-case audit using the standard library."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import sys
from export_redaction import verify as verify_portable_export

ROOT=Path(__file__).resolve().parent
def load(p):
    b=(ROOT/p).read_bytes()
    return json.loads(gzip.decompress(b) if p.endswith(".gz") else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def manifest():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name!="MANIFEST_SHA256.json" and "__pycache__" not in p.parts}
def main():
    if "--write-manifest" in sys.argv:(ROOT/"MANIFEST_SHA256.json").write_text(json.dumps(manifest(),sort_keys=True,indent=2),encoding="utf8")
    assert load("MANIFEST_SHA256.json")==manifest()
    verify_portable_export()
    for folder in ("","challenge/","census/"):
        for n,h in load(folder+"forecast-seal.json").items():assert sha(ROOT/folder/n)==h
    p=load("plan.json")
    prior=set(p["all_prior"]);already=set()
    for r in p["cohort"]:
        shas={r[k] for k in ("current","true_parent","direct_parent")}
        assert not shas&prior and not already&shas;already|=shas
    assert [r["current"] for r in p["cohort"]]==[r["current"] for r in p["flow"] if r.get("selected")]
    src=load("forecasts.json.gz");actual=load("current-runs.json.gz")
    assert len(src)==70 and len(actual)==56
    rr={(r["current"],r["file"]):r for r in src}
    after={(r["current"],r["file"]):r for r in actual}
    cases=load("cases.json.gz");pairs=load("pair-results.json");stats=load("results.json")
    def phases(r):
        out={}
        for n,f,s in (r["results"] or {}).get("phases",[]):out.setdefault(n,{})[f]=s
        return out
    for case in cases:
        r=rr[case["current"],case["file"]]
        assert case["raw_clean"]==r["clean"]
        for arm,flag in r["pred"].items():assert flag==case["pred"][arm]
        if case["panel"]=="new":
            now=after[case["current"],case["file"]];b,a=phases(r),phases(now);same=b.keys()&a.keys()
            fail=sorted(n for n in same if b[n].get("call")=="passed" and "failed" not in b[n].values() and "failed" in a[n].values())
            assert fail==case["pass_to_fail"] and sorted(b.keys()-a.keys())==case["old_only"] and sorted(a.keys()-b.keys())==case["new_only"]
    for p in pairs:
        these=[r for r in cases if r["current"]==p["current"]]
        gold={r["file"] for r in these if r["affected"]}
        for arm,v in p["methods"].items():
            s={r["file"] for r in these if r["pred"][arm]}
            assert s==set(v["selected"]) and set(v["tp"])==s&gold and set(v["fn"])==gold-s
    h=stats["new"]
    assert h["metrics"]["projected"]["selected"]==42 and h["metrics"]["NameRTS"]["selected"]==17 and h["affected"]==16
    synth=load("challenge/results.json");expanded=load("census/results.json")
    assert len(synth["cases"])==35 and synth["fail_count"]==6
    old=load("census/forecasts.json.gz")
    assert len(old)==expanded["n"]==48
    assert {r["file"] for r in old if r["pred"]["stat_guard"]}==set(expanded["methods"]["stat_guard"]["selected"])
    print("OK",len(manifest()),"files; 70 primary/calibration forecasts, 56 actual new SHA runs, 35 synthetic scenarios and 48-file census.")
if __name__=="__main__":main()
