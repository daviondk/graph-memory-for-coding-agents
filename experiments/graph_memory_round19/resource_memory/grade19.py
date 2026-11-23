from collections import Counter
from pathlib import Path
from statistics import mean
import json
import math
from plan19 import ROOT,old
from experiment import check,ast_equal
from score import FILES

def states(r):
    s={}
    for n,ph,st in (r["results"] or {}).get("phases",[]):s.setdefault(n,{})[ph]=st
    return s
def score():
    check()
    seal=old.load(ROOT/"forecast-seal.json")
    assert all(old.sha((ROOT/p).read_bytes())==v for p,v in seal.items())
    plan=old.load(ROOT/"plan.json");base=old.load(ROOT/"forecasts.json.gz");current=old.load(ROOT/"current-runs.json.gz")
    comp={(r["current"],r["file"]):r for r in current}
    sources={};author={}
    for label,filename in FILES.items():
        data=old.git("show",old.VERSION+":"+filename,where=old.PKG);sources[label]={"sha256":old.sha(data),"path":filename,"revision":old.VERSION}
        author[label]={r["current"]:r for r in json.loads(data) if r.get("target",True)}
    old.put(ROOT/"author-sources.json",sources)
    pairs=[];rs=[]
    for p in plan["cohort"]+plan["calibration"]:
        c=p["current"];ms={k:author[k][c] for k in author}
        assert ms["gold"]["true_parent"]==p["true_parent"] and ms["gold"]["direct_parent"]==p["direct_parent"]
        for k,data in ms.items():
            if data.get("true_parent"):assert data["true_parent"]==p["true_parent"]
        subset=[r for r in base if r["current"]==c]
        assert len(subset)==len(p["tests"]) and {r["file"] for r in subset}==set(p["tests"])
        predset={r["file"]:dict(r["pred"]) for r in subset}
        for r in subset:
            f=r["file"]
            predset[f].update({k:f in d["tests_to_run"] for k,d in ms.items() if k!="gold"})
            before=states(r);bpass={n for n,s in before.items() if s.get("call")=="passed" and "failed" not in s.values()}
            a=comp.get((c,f))
            out=dict(file=f,current=c,base=p["true_parent"],panel=p["panel"],affected=f in ms["gold"]["tests_to_run"],raw_clean=r["clean"],pred=predset[f],
                 reasons=r["reasons"],n_base=len(before),base_pass=len(bpass),reads=(r["results"] or {}).get("resource_reads",{}),
                 opaque=(r["results"] or {}).get("subprocess_events",[]))
            if a:
                after=states(a); common=before.keys()&after.keys()
                bad={n for n in bpass&common if "failed" in after[n].values()}
                again={n for n in bpass&common if after[n].get("call")=="passed" and "failed" not in after[n].values()}
                out.update(current_clean=a["clean"],current_rc=a["rc"],pytest_rc=(a["results"] or {}).get("pytest_rc"),
                    common=len(common),same_pass=len(again),pass_to_fail=sorted(bad),
                    pass_to_skip_incomplete=sorted((bpass&common)-bad-again),old_only=sorted(before.keys()-after.keys()),
                    new_only=sorted(after.keys()-before.keys()),changed_phase=sorted(n for n in common if before[n]!=after[n]),
                    all_after_fail=sorted(n for n,phase in after.items() if "failed" in phase.values()),
                    all_before_fail=sorted(n for n,phase in before.items() if "failed" in phase.values()))
            rs.append(out)
        tset=set(p["tests"]);gold=tset&set(ms["gold"]["tests_to_run"]);arms={}
        for name in next(iter(predset.values())):
            chosen={f for f,opts in predset.items() if opts[name]};miss=gold-chosen
            arms[name]={"selected":sorted(chosen),"tp":sorted(chosen&gold),"fp":sorted(chosen-gold),"fn":sorted(miss)}
        pairs.append(dict(current=c,base=p["true_parent"],panel=p["panel"],truth=sorted(gold),gold_all=ms["gold"]["tests_to_run"],n=len(tset),
            ast_equal=ast_equal(p),methods=arms))
    old.put(ROOT/"cases.json.gz",rs);old.put(ROOT/"pair-results.json",pairs)
    result={}
    for group in ("new","calibration"):
        pa=[r for r in pairs if r["panel"]==group];rr=[r for r in rs if r["panel"]==group]
        names=pa[0]["methods"].keys();agg={}
        for arm in names:
            agg[arm]={k:sum(len(p["methods"][arm][k]) for p in pa) for k in ("selected","tp","fp","fn")}
            agg[arm]["per_pair_selected"]=[len(p["methods"][arm]["selected"]) for p in pa]
            if group=="new":
                agg[arm]["false_reuse_after_pass_to_fail_count"]=sum(bool(r["pass_to_fail"]) and not r["pred"][arm] for r in rr)
        sums={}
        if group=="new":
            for field in ("n_base","base_pass","common","same_pass","pass_to_fail","pass_to_skip_incomplete","old_only","new_only","changed_phase","all_after_fail","all_before_fail"):
                sums[field]=sum(len(r[field]) if type(r[field]) is list else r[field] for r in rr)
        result[group]={"n":len(rr),"clean":sum(r["raw_clean"] for r in rr),"affected":sum(r["affected"] for r in rr),
            "metrics":agg,"actual":sums,"base_seconds":sum(r["seconds"] for r in base if r["panel"]==group),
            "current_seconds":sum(r["seconds"] for r in current if r["panel"]==group),"base_item_pass":sum(r["base_pass"] for r in rr)}
    old.put(ROOT/"results.json",result)
    print(result,flush=True)
if __name__=="__main__":score()
