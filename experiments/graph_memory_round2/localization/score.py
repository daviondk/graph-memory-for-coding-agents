"""Join official function edit annotations only after all five-slot predictions were locked."""
import collections, gzip,hashlib,json,math
from pathlib import Path
import random
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def measures(pred,gold):
    inter=len(set(pred[:5])&gold)
    return {"official_acc1":int(len(set(pred[:1])&gold)==min(1,len(gold))),
            "official_acc3":int(len(set(pred[:3])&gold)==min(3,len(gold))),
            "official_acc5":int(inter==min(5,len(gold))),"complete5":int(gold<=set(pred[:5])),
            "hit5":int(inter>0),"recall5":inter/len(gold)}
def compare(rows,a,b,k="official_acc5"):
    vals=[r["arms"][a][k]-r["arms"][b][k] for r in rows]
    by=collections.defaultdict(list)
    for r,d in zip(rows,vals):by[r["repo"]].append(d)
    names=sorted(by)
    pairs=[(sum(by[g]),len(by[g])) for g in names]
    rng=random.Random(20261118);effects=[]
    for _ in range(20000):
        sample=rng.choices(pairs,k=len(pairs))
        effects.append(sum(v for v,n in sample)/sum(n for v,n in sample))
    effects.sort()
    def quant(q):
        ix=(len(effects)-1)*q
        lo=math.floor(ix)
        return effects[lo]+(ix-lo)*(effects[min(lo+1,len(effects)-1)]-effects[lo])
    wins=sum(d>0 for d in vals);loss=sum(d<0 for d in vals);disc=wins+loss
    p=min(1,2*sum(math.comb(disc,j) for j in range(min(wins,loss)+1))/(2**disc))
    return dict(n=len(rows),delta=float(sum(vals)/len(vals)),interval=[quant(.025),quant(.975)],
                wins=wins,ties=vals.count(0),losses=loss,discordant_p=p,repo_net={k:sum(by[k]) for k in names})
def main():
    lock=json.loads((ROOT/"prediction_lock.json").read_text())
    for f,h in lock.items():assert sha(ROOT/f)==h
    data=pq.read_table(ROOT/"input/locagent_test.parquet",columns=["instance_id","edit_functions"]).to_pylist()
    labels={r["instance_id"]:{f.split(":")[0] for f in r["edit_functions"]} for r in data}
    out=[]
    for s in (ROOT/"predictions.jsonl").read_text().splitlines():
        r=json.loads(s);g=labels[r["id"]]
        if not g:continue
        out.append({"id":r["id"],"repo":r["repo"],"date":r["date"],"status":r["reason"],"ngold":len(g),
                    "gold":sorted(g),"arms":{a:measures(p,g) for a,p in r["ranks"].items()}})
    by=collections.defaultdict(list)
    for r in out:by[r["repo"]].append(r)
    latest={r["id"] for rr in by.values() for r in sorted(rr,key=lambda x:(x["date"],x["id"]))[len(rr)//2:]}
    scores={}
    for group,rows in [("all",out),("later",[r for r in out if r["id"] in latest]),("vacant",[r for r in out if r["status"]=="completed"])]:
        arms=list(rows[0]["arms"])
        scores[group]={"n":len(rows),"repos":len({r["repo"] for r in rows}),
            "totals":{a:{m:sum(r["arms"][a][m] for r in rows) for m in rows[0]["arms"][a]} for a in arms},
            "pair":{f"event-{a}":compare(rows,"event",a) for a in arms if a!="event"},
            "vs_native":{a:compare(rows,a,"native") for a in arms if a!="native"}}
    scores["source"]={"data":sha(ROOT/"input/locagent_test.parquet"),"scorer":sha(ROOT/"input/eval_metric.py"),
                      "rows":len(data),"empty_annotated":sum(not v for v in labels.values()),"predictions":lock["predictions.jsonl"]}
    (ROOT/"scored.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in out),encoding="utf8")
    (ROOT/"results.json").write_text(json.dumps(scores,indent=2),encoding="utf8")
    for k in ("all","later","vacant"):
        v=scores[k];print(k,v["n"],{a:(b["official_acc5"],b["complete5"],b["hit5"]) for a,b in v["totals"].items()})
        for x in ["event-direct","event-flat","event-native","event-placebo"]:
            z=v["pair"][x];print(x,z["wins"],z["losses"],z["interval"])
if __name__=="__main__":main()


