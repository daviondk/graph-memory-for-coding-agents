from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import importlib.util
import sys
import tempfile
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent
sys.path.insert(0,str(PARENT))
from plan19 import old
import experiment
from score import FILES
import json
def guarded(row):
    runtime=row.get("runtime") or row.get("results")
    return row["pred"]["projected"] or not runtime or any(runtime["stat_reads"].values()) or bool(runtime["stat_unknown"])
def chosen(rs,name):return sorted(r["file"] for r in rs if (guarded(r) if name=="stat_guard" else r["pred"][name]))
def candidate():
    plan=old.load(PARENT/"plan.json")
    ps=[p for p in plan["cohort"] if any(x["kind"]=="stub" for x in p["resources"].values())]
    assert len(ps)==1
    p=ps[0];p["ast_equal"]=experiment.ast_equal(p);p["tests"]=p["pool"]
    p["hashes"]={s:{f:old.sha(old.git("show",c+":"+f)) for f in p["tests"]} for s,c in (("base",p["true_parent"]),("current",p["current"]))}
    return p
def main():
    experiment.check()
    plan={n:old.sha((ROOT/n).read_bytes()) for n in ("PROTOCOL_RU.md","observe.py","run_census.py")}
    old.put(ROOT/"plan-seal.json",plan)
    p=candidate()
    with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
        scratch=Path(scratch);experiment.ROOT=ROOT
        for stage in ("base","current"):
            sha=p["true_parent"] if stage=="base" else p["current"]
            tar=scratch/(sha+".tar");tar.write_bytes(old.git("archive","--format=tar",sha))
            with ThreadPoolExecutor(max_workers=5) as pool:
                rows=list(pool.map(experiment.run,[(p,f,stage,tar,scratch) for f in p["tests"]]))
            if stage=="base":
                for r in rows:r["pred"]["stat_guard"]=bool(guarded(r))
                base=rows;old.put(ROOT/"forecasts.json.gz",rows)
                old.put(ROOT/"forecast-seal.json",{n:old.sha((ROOT/n).read_bytes()) for n in ("forecasts.json.gz","plan-seal.json")})
            else:current=rows;old.put(ROOT/"current.json.gz",rows)
        spec=importlib.util.spec_from_file_location("resource_challenge",PARENT/"challenge/challenge.py");ch=importlib.util.module_from_spec(spec);spec.loader.exec_module(ch)
        ch.ROOT=ROOT/"child"
        with ThreadPoolExecutor(max_workers=5) as pool:
            synth=list(pool.map(ch.one,[(m,t,path,"base",scratch) for m,(path,_) in ch.mutations.items() for t in ch.tests]))
        old.put(ROOT/"challenge-base.json.gz",synth)
        known={(r["mutation"],r["file"]):r["failed"] for r in old.load(PARENT/"challenge/results.json")["cases"]}
        result_s={"selected":sum(bool(guarded(r)) for r in synth),"caught":sum(bool(guarded(r)) and known[r["mutation"],r["file"]] for r in synth),
            "failed":sum(known.values()),"changed_policy":[[r["mutation"],r["file"]] for r in synth if bool(guarded(r))!=r["pred"]["projected"]]}
    c=p["current"];authors={k:next(r for r in json.loads(old.git("show",old.VERSION+":"+v,where=old.PKG)) if r["current"]==c) for k,v in FILES.items()}
    for r in authors.values():
        if r.get("true_parent"):assert r["true_parent"]==p["true_parent"]
    truth=set(authors["gold"]["tests_to_run"])
    assert truth<=set(p["pool"])
    methods={k:chosen(base,k) for k in ("previous","path","projected","stat_guard")}
    methods.update({k:sorted(set(r["tests_to_run"])&set(p["pool"])) for k,r in authors.items() if k!="gold"})
    oldbase={r["file"]:r for r in old.load(PARENT/"forecasts.json.gz") if r["current"]==c}
    drift=[r["file"] for r in base if r["file"] in oldbase and (r["pred"]["projected"]!=oldbase[r["file"]]["pred"]["projected"] or r["clean"]!=oldbase[r["file"]]["clean"])]
    metric={k:{"selected":v,"hits":sorted(set(v)&truth),"missed":sorted(truth-set(v))} for k,v in methods.items()}
    def states(r):
        s={}
        for n,p,v in (r["results"] or {}).get("phases",[]):s.setdefault(n,{})[p]=v
        return s
    transitions={};same=0;common=0;added=0;gone=0
    for b,a in zip(base,current,strict=True):
        assert b["file"]==a["file"];x,y=states(b),states(a);inter=x.keys()&y.keys()
        f=[n for n in inter if x[n].get("call")=="passed" and "failed" not in x[n].values() and "failed" in y[n].values()]
        if f:transitions[b["file"]]=f
        same+=sum(x[n].get("call")=="passed" and y[n].get("call")=="passed" and "failed" not in x[n].values() and "failed" not in y[n].values() for n in inter);common+=len(inter)
        added+=len(y.keys()-x.keys());gone+=len(x.keys()-y.keys())
    result={"n":len(base),"clean":sum(r["clean"] for r in base),"current_clean":sum(r["clean"] for r in current),"truth":sorted(truth),"methods":metric,
        "prior_drift":drift,"current_pass_to_fail":transitions,"same_pass":same,"common_items":common,"new_only":added,"old_only":gone,"guard_challenge":result_s,
        "stat_hits":[r["file"] for r in base if any((r["results"] or {}).get("stat_reads",{}).values())],
        "open_hits":[r["file"] for r in base if any((r["results"] or {}).get("resource_reads",{}).values())],
        "opaque":[r["file"] for r in base if (r["results"] or {}).get("subprocess_events")], "unknown":[r["file"] for r in base if not r["clean"]],
        "base_seconds":sum(r["seconds"] for r in base),"after_seconds":sum(r["seconds"] for r in current)}
    old.put(ROOT/"results.json",result);print({k:len(v) for k,v in methods.items()},"affected",len(truth),result_s,flush=True)
if __name__=="__main__":main()
