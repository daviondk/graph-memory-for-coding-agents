from concurrent.futures import ThreadPoolExecutor
import json
from plan import ROOT,CACHE,load,put,sha,git,PKG,VERSION
from frequency import jobs_for,close
from forecast import run_one
from score import combine,table,FILES

def main():
    extra=load(ROOT/"supplemental-plan.json");old=load(ROOT/"supplemental-forecasts.gz");todo=[];plans=[]
    assert len(extra)==1
    for p in extra:
        remaining=[f for f in p["pool"] if f not in p["tests"]]
        allp={**p,"test_sha":{f:sha(git("show",p["true_parent"]+":"+f)) for f in p["pool"]}}
        plans.append(allp)
    close(("FULL_CENSUS_RU.md","census.py","frequency-seal.json"),"census-lock.json")
    retained=CACHE/("census-"+sha((ROOT/"census-lock.json").read_bytes())[:18]);retained.mkdir(exist_ok=True)
    for p in plans:
        todo.extend(jobs_for(p,[f for f in p["pool"] if f not in p["tests"]],retained))
    with ThreadPoolExecutor(max_workers=5) as pool:out=list(pool.map(run_one,todo))
    put(ROOT/"census-extra-forecasts.gz",out)
    close(("census-lock.json","census-extra-forecasts.gz","supplemental-forecasts.gz"),"census-seal.json")
    authors={k:{r["current"]:r for r in json.loads(git("show",VERSION+":"+path,where=PKG)) if r.get("target",True)} for k,path in FILES.items()}
    rows=old+out;assert len(rows)==48==len({r["file"] for r in rows})
    result=combine(plans,rows,authors)
    put(ROOT/"census-results.json",{"pairs":result,"aggregate":table(result),"clean":sum(r["clean"] for r in rows),
        "passes":sum(r["passes"] for r in rows),"wall_s":sum(r["wall_s"] for r in rows)})
    print(table(result),sum(r["clean"] for r in rows),sum(r["passes"] for r in rows),flush=True)
if __name__=="__main__":main()
