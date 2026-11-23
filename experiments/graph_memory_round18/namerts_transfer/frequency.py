from concurrent.futures import ThreadPoolExecutor
from plan import ROOT,CACHE,load,put,sha,git,features,testfiles
from forecast import run_one

def close(n,target):
    put(ROOT/target,{name:sha((ROOT/name).read_bytes()) for name in n})

def jobs_for(pair,tests,retained):
    tar=CACHE/(pair["true_parent"]+".tar")
    if not tar.exists():tar.write_bytes(git("archive","--format=tar",pair["true_parent"]))
    return [(pair,test,tar,retained,CACHE/"runs") for test in tests]

def main():
    plan=load(ROOT/"plan.json")
    primary={p["current"]:p for p in plan["cohort"]}
    flow=[];extra=[]
    for row in plan["flow"]:
        if row["eligibility"]!="candidate":continue
        c=row["current"];b=row["true_parent"]
        src=primary.get(c) or features(b,c)
        gains=[p for p,m in src["modules"].items() if m["change"]["old_fallback"] and not m["change"]["new_fallback"]]
        eligible=bool(gains and not src["force_all"])
        flow.append({"current":c,"true_parent":b,"gains":gains,"global":src["force_all"],"eligible":eligible,"primary":c in primary})
        if not eligible or c in primary or len(extra)>=3:continue
        pool=sorted(testfiles(b)&testfiles(c),key=lambda f:sha(("file-r18|"+c+"|"+f).encode()))
        extra.append({**row,**src,"pool":pool,"tests":pool[:20],"test_sha":{f:sha(git("show",b+":"+f)) for f in pool[:20]}})
    put(ROOT/"mechanism-frequency.json",flow);put(ROOT/"supplemental-plan.json",extra)
    close(("FREQUENCY_PROTOCOL_RU.md","frequency.py","forecast-seal.json","mechanism-frequency.json","supplemental-plan.json"),"frequency-lock.json")
    retained=CACHE/("followup-"+sha((ROOT/"frequency-lock.json").read_bytes())[:16]);retained.mkdir(exist_ok=True)
    tasks=[];actual=[]
    for p in extra:tasks.extend(jobs_for(p,p["tests"],retained))
    adult=retained/"current";adult.mkdir(exist_ok=True)
    for p in primary.values():
        c=p["current"];files=p["tests"][:3]
        pseudo={"current":c,"true_parent":c,"test_sha":{f:sha(git("show",c+":"+f)) for f in files},"modules":{},"force_all":[],"edited_tests":[]}
        actual.extend(jobs_for(pseudo,files,adult))
    with ThreadPoolExecutor(max_workers=5) as pool:
        extra_rows=list(pool.map(run_one,tasks));actual_rows=list(pool.map(run_one,actual))
    put(ROOT/"supplemental-forecasts.gz",extra_rows);put(ROOT/"current-actual.gz",actual_rows)
    close(("frequency-lock.json","supplemental-forecasts.gz","current-actual.gz"),"frequency-seal.json")
    print("frequency",len(flow),sum(bool(r["gains"]) for r in flow),sum(r["eligible"] for r in flow),"extra",len(extra),"actual",len(actual_rows),flush=True)
if __name__=="__main__":main()
