"""Grade only after every policy decision has been sealed; every method reuses same candidate scores."""
import collections,concurrent.futures,gzip,json,math,random,statistics,sys
from pathlib import Path
from prepare import HERE,OLD,read,save,sha
sys.path.append(str(OLD))
from runner import execute
import numpy

def signp(a,b):
    n=a+b
    return min(1.,2*sum(math.comb(n,k) for k in range(min(a,b)+1))/(2**n)) if n else 1.
def contrast(d):
    n=len(d);randomizer=random.Random(182611)
    if not n:return None
    draws=sorted(sum(randomizer.choices(d,k=n))/n for _ in range(10000))
    wins=d.count(1);loss=d.count(-1)
    return dict(n=n,wins=wins,losses=loss,equal=n-wins-loss,delta=sum(d)/n,ci=[draws[249],draws[9749]],p=signp(wins,loss))
def grade(task):
    row,enh=task;i=row["id"];entry=row["entry"]
    path=HERE/"grading"/str(i);path.mkdir(exist_ok=True,parents=True)
    ref=path/"reference.py";ref.write_text(enh["code"],encoding="utf8")
    stub=path/"stub.py";stub.write_text("def "+row["sig"]+":\n    raise NotImplementedError\n",encoding="utf8")
    setup=["import os; os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'",
           "import sys; sys.path.append("+repr(str(Path(numpy.__file__).resolve().parent.parent))+")"]+enh["test_imports"]
    paths={str(j):HERE/"programs"/str(i)/f"{j}.py" for j in range(3)}
    paths.update(reference=ref,stub=stub)
    scores={};cache={}
    for a,p in paths.items():
        h=sha(p.read_bytes())
        if h not in cache:cache[h]=execute(p,entry,setup,[enh["test"]])
        scores[a]={"sha256":h,**cache[h]}
    save(path/"receipt.json",scores)
    return i,scores
def main():
    seal=read(HERE/"decision_lock.json")
    for f,h in seal.items():assert sha((HERE/f).read_bytes())==h
    checks=read(HERE/"candidate_lock.json")
    assert all(sha((HERE/name).read_bytes())==v for name,v in checks.items())
    assert sha((OLD/"mbppplus.jsonl.gz").read_bytes())==read(HERE/"input_lock.json")["sources"]["mbppplus.jsonl.gz"]
    enhanced={int(r["task_id"]):r for l in gzip.decompress((OLD/"mbppplus.jsonl.gz").read_bytes()).splitlines() if (r:=json.loads(l))}
    items=read(HERE/"inputs.json")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        scored=dict(pool.map(grade,[(it,enhanced[it["id"]]) for it in items]))
    total={}
    for panel in ("fresh","old"):
        rows=read(HERE/("decisions_"+panel+".json"));observed={r["id"]:r for r in read(HERE/("observed_"+panel+".json"))}
        metrics=[]
        for r in rows:
            i=r["id"];s=scored[i];o=observed[i]
            hit={arm:int(s[str(j)]["status"]=="pass") for arm,j in r["decisions"].items()}
            hit["pool_oracle"]=int(any(s[str(j)]["status"]=="pass" for j in range(3)))
            hit["reference"]=int(s["reference"]["status"]=="pass")
            hit["stub"]=int(s["stub"]["status"]=="pass")
            hit["public_pool_oracle"]=int(any(s[str(j)]["status"]=="pass" for j in range(3) if o["arms"][j]["public"]==max(a["public"] for a in o["arms"])))
            metrics.append({"id":i,"hit":hit,"informative":bool(r["admissible"]),"arms":r["decisions"],"used":r["used"],"responses":r["answers"]})
        save(HERE/("item_scores_"+panel+".json"),metrics)
        arms=list(metrics[0]["hit"])
        def summary(sub):
            if not sub:return {}
            return {"n":len(sub),"solved":{a:sum(r["hit"][a] for r in sub) for a in arms},
                "value_minus":{a:contrast([r["hit"]["value"]-r["hit"][a] for r in sub]) for a in ("short","gini","uniform","static","first_public","single","placebo")},
                "chosen_probes_vs_short":sum(r["used"].get("value")!=r["used"].get("short") for r in sub),
                "chosen_candidate_vs_short":sum(r["arms"]["value"]!=r["arms"]["short"] for r in sub)}
        total[panel]={"all":summary(metrics),"informed":summary([r for r in metrics if r["informative"]]),
                      "reference_ok":summary([r for r in metrics if r["hit"]["reference"] and not r["hit"]["stub"]]),
                      "states":dict(collections.Counter(v["status"] for r in rows for v in scored[r["id"]].values())),
                      "physical_judge_calls":sum(len(r["answers"]) for r in rows),
                      "judge_tokens":{a:{label:sum(r["answers"][str(r["used"][a])]["usage"][label] for r in rows if a in r["used"])
                      for label in ("prompt_tokens","completion_tokens")} for a in ("uniform","short","value","gini","placebo")}}
    save(HERE/"results.json",total)
    for k,s in total.items():print(k,s["all"]["n"],s["all"]["solved"],s["all"]["value_minus"]["short"],"informative",s["informed"].get("n",0),"reader_calls",s["physical_judge_calls"])
if __name__=="__main__":main()

