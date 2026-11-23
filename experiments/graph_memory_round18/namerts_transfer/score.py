"""Compare sealed predictions with author labels only on the exact same revisions and test files."""
import collections
import itertools
import math
import subprocess
from plan import ROOT,OLD,PKG,VERSION,git,load,put,sha,GIT
from forecast import select

FILES={"gold":"ground truth/gt_loguru.json","NameRTS":"results/rq1/namerts/NameBDP_RTSTest_LOG.json",
       "EkstaP":"results/rq1/ekstap/EkstaP_RTSTest_LOG.json","BabelRTS":"results/rq1/babelrts/BabelRTS_loguru_clearn.json"}
def table(pairs):
    keys=list(pairs[0]["methods"])
    return {k:{"checked":sum(len(p["methods"][k]["selected"]) for p in pairs),
               "hits":sum(len(p["methods"][k]["hits"]) for p in pairs),
               "misses":sum(len(p["methods"][k]["misses"]) for p in pairs),
               "saves_all_affected_changes":sum(not p["methods"][k]["misses"] for p in pairs)}
            for k in keys}
def stats(pairs,k,baseline):
    d=[len(r["methods"][baseline]["selected"])-len(r["methods"][k]["selected"]) for r in pairs]
    pos=sum(v>0 for v in d);neg=sum(v<0 for v in d)
    vals=sorted(sum(d[i] for i in draw)/sum(pairs[i]["units"] for i in draw) for draw in itertools.product(range(len(d)),repeat=len(d)))
    return {"net_saved":sum(d),"per_revision":d,"positive":pos,"negative":neg,"ties":len(d)-pos-neg,
            "exact_two_sided_sign_p":min(1.,2*sum(math.comb(pos+neg,j) for j in range(min(pos,neg)+1))/2**(pos+neg)),
            "commit_bootstrap_percentiles":[vals[int(.025*(len(vals)-1))],vals[int(.975*(len(vals)-1))]]}
def combine(plans,forecasts,authors):
    result=[]
    for p in plans:
        c=p["current"];rows=[r for r in forecasts if r["current"]==c];assert rows
        g=authors["gold"][c];assert g["true_parent"]==p["true_parent"]
        if "direct_parent" in p:assert g["direct_parent"]==p["direct_parent"]
        tests={r["file"] for r in rows};assert len(tests)==len(rows)
        if "pool" in p:assert set(g["tests_to_run"])<=set(p["pool"]) | set(p["edited_tests"])
        truth=set(g["tests_to_run"]) & tests
        raw={k:{r["file"] for r in rows if r["policies"][k]} for k in rows[0]["policies"]}
        for k in ("NameRTS","BabelRTS","EkstaP"):
            pred=authors[k][c]
            for name,expected in (("true_parent",p["true_parent"]),("direct_parent",g["direct_parent"])):
                if pred.get(name) is not None:assert pred[name]==expected,(k,c,name)
            raw[k]=tests & set(pred["tests_to_run"])
        arms={k:{"selected":sorted(v),"hits":sorted(truth&v),"misses":sorted(truth-v),"extra":sorted(v-truth)} for k,v in raw.items()}
        cleaned={r["file"] for r in rows if r["clean"]}
        result.append({"current":c,"true_parent":p["true_parent"],"units":len(tests),"official_n":g["total_tests"],
                       "pool_n":len(p.get("pool",[])) or None,"official_true":len(g["tests_to_run"]),"truth":sorted(truth),
                       "clean_files":sorted(cleaned),"unconfirmed":sorted(tests-cleaned),"baseline_pass_items":sum(r["passes"] for r in rows),
                       "methods":arms,"seconds":sum(r["wall_s"] for r in rows)})
    return result
def main():
    assert all(sha((ROOT/n).read_bytes())==h for n,h in load(ROOT/"forecast-seal.json").items())
    plan=load(ROOT/"plan.json");out=load(ROOT/"forecasts.gz")
    import json
    authors={};source={}
    for k,path in FILES.items():
        blob=git("show",VERSION+":"+path,where=PKG);native=json.loads(blob)
        assert native==load(PKG/path)
        authors[k]={r["current"]:r for r in native if r.get("target",True)}
        source[k]={"sha":sha(blob),"git_object":git("rev-parse",VERSION+":"+path,where=PKG).decode().strip(),"revision":VERSION,"path":path}
    put(ROOT/"author-sources.json",source)
    result=combine(plan["cohort"],out,authors);put(ROOT/"paired.json",result)
    calibration=[];existing=load(OLD/"transfer-predictions.json.gz")
    for p in plan["known_calibration"]:
        for r in existing:
            if r["current"]!=p["current"]:continue
            t=r["runtime"]
            tr={p["module"]:{"lines":t["lines"],"calls":t["calls"]}}
            pred=select(p,r["file"],tr,r["clean"])
            assert pred["old_function"]==r["select"]["function"] and pred["old_line"]==r["select"]["line"]
            calibration.append({"current":r["current"],"file":r["file"],"clean":r["clean"],"passes":r["pass_count"],"policies":pred,"wall_s":t["seconds"]})
    old_result=combine(plan["known_calibration"],calibration,authors);put(ROOT/"calibration.json",old_result)
    report={"aggregate":table(result),"calibration":table(old_result),"units":len(out),"clean":sum(r["clean"] for r in out),
            "base_items":sum(r["passes"] for r in out),"baseline_wall_s_sum":sum(r["wall_s"] for r in out),
            "clean_only":{k:{"checked":sum(len(set(r["methods"][k]["selected"])&set(r["clean_files"])) for r in result),
                             "hits":sum(len(set(r["methods"][k]["hits"])&set(r["clean_files"])) for r in result),
                             "misses":sum(len(set(r["methods"][k]["misses"])&set(r["clean_files"])) for r in result)} for k in result[0]["methods"]},
            "relative_count":{k:stats(result,"outer_function",k) for k in ("old_function","module","NameRTS")}}
    put(ROOT/"results.json",report);print(report["aggregate"]);print("calibration",report["calibration"])
if __name__=="__main__":main()
