import collections,gzip,hashlib,itertools,json,math,random,statistics,sys
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def exact(w,l):
    n=w+l
    return min(1,2*sum(math.comb(n,k) for k in range(min(w,l)+1))/2**n)
def main():
    ids=read(D/"cohort.json")["ids"];rows=[];reg=collections.Counter();den=collections.Counter();arms=["flat","graph","shuffled"]
    for i in ids:
        t=D/"tasks"/i;ctl=read(t/"grades_v2/control.json");new=read(t/"grades_v2/solver.json");p=read(t/"packets.json.gz")
        bf=ctl["base"]["tests"]["FAIL_TO_PASS"];gf=ctl["gold"]["tests"]["FAIL_TO_PASS"]
        valid=bool(bf["complete"] and bf["failed"] and gf["complete"] and not gf["failed"])
        gold=ctl["gold"]["gold_lines"];sites={(path,n) for path,lines in gold.items() for n in lines}
        basep=ctl["base"]["tests"]["PASS_TO_PASS"];row={"id":i,"valid":valid,"base_f2p":bf,"gold_f2p":gf,"sites":len(sites),"visible":len([x for x in sites if x[0] in p["paths"]]),"paths":p["paths"],"nodes":p["nodes"],"edges":p["edges"],"blocks":p["blocks"],"arms":{}}
        for arm in arms:
            a=new[arm];f=a["tests"]["FAIL_TO_PASS"];rp=a["tests"]["PASS_TO_PASS"];kept={(file,n) for file,st,en in p["kept"][arm] for n in range(st,en+1)}
            rbase=set(basep["passed"]);rcand=set(rp["passed"])
            mark=bool(valid and a["applied"] and f["complete"] and not f["failed"])
            row["arms"][arm]={"applied":a["applied"],"passed":mark,"reason":a["reason"],"recall":len(kept&sites)/len(sites) if sites else None,"hit":bool(kept&sites),"cover":len(kept&sites),"tokens":p["tokens"][arm],"passed_f2p":len(f["passed"]),"observed_regressions":sorted(rbase&set(rp["failed"])),"missing_previously_passing":sorted(rbase-rcand),"base_p2p":len(rbase),"call":a["call_id"]}
        rows.append(row)
    metrics={}
    for arm in arms:
        sub=[r["arms"][arm] for r in rows];sel=[r["arms"][arm] for r in rows if r["valid"]]
        metrics[arm]={"n":len(rows),"valid":len(sel),"valid_pass":sum(x["passed"] for x in sel),"applied":sum(x["applied"] for x in sub),"any_gold_line":sum(x["hit"] for x in sub),"covered_lines":sum(x["cover"] for x in sub),"macro_coverage":statistics.mean(x["recall"] for x in sub if x["recall"] is not None),"mean_tokens":statistics.mean(x["tokens"] for x in sub),"observed_regressions":sum(len(x["observed_regressions"]) for x in sub),"missing_p2p":sum(len(x["missing_previously_passing"]) for x in sub),"base_p2p":sum(x["base_p2p"] for x in sub)}
    pairs={}
    for arm in ["flat","shuffled"]:
        for metric in ["passed","hit","applied"]:
            rr=[r for r in rows if r["valid"] or metric!="passed"];d=[int(r["arms"]["graph"][metric])-int(r["arms"][arm][metric]) for r in rr];w=d.count(1);l=d.count(-1)
            pairs[arm+"_"+metric]={"wins":w,"losses":l,"p":exact(w,l),"n":len(rr)}
    result={"metrics":metrics,"pairs":pairs,"n_gold_lines":sum(x["sites"] for x in rows),"n_visible":sum(x["visible"] for x in rows),"visible_tasks":sum(bool(x["visible"]) for x in rows),"with_calls":len(list((D/"calls").glob("*.gz"))),"test_tasks":ids,"total_tokens":{}}
    for name in ["prompt_tokens","completion_tokens"]:result["total_tokens"][name]=sum(read(p)["response"]["usage"][name] for p in (D/"calls").glob("*.gz"))
    (D/"per_task.json").write_text(json.dumps(rows,indent=1),encoding="utf8");(D/"results.json").write_text(json.dumps(result,indent=1),encoding="utf8")
    print(json.dumps(result["metrics"]))
if __name__=="__main__":main()


