"""Evaluate held-out local predictions at the fixed cost with paired cluster intervals."""
import gzip,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/"native_revisions"))
from prepare import views,metrics,hashkey
from fetch import checksum
def main():
    path=HERE/"forecasts.json.gz";j=json.loads((HERE/"forecast-seal.json").read_bytes());assert j["forecasts"]==checksum(path)
    rows=json.loads(gzip.decompress(path.read_bytes()));old,new=views("original"),views("edits")
    qs=sorted(rows);groups=sorted({r["group"] for r in rows.values()})
    membership=np.asarray([[rows[q]["group"]==g for q in qs] for g in groups],dtype=float);sizes=membership.sum(axis=1)
    draws=np.random.default_rng(293330).integers(len(groups),size=(20000,len(groups)))
    quotas=(0,len(qs)//10,len(qs)//3,len(qs)//2,len(qs));tables={}
    source={}
    for q,r in rows.items():
        old_em=metrics(r["old"]["text"],old[q][1])[1];source[q]={}
        for mode in ("old","new"):
            f,e=metrics(r[mode]["text"],new[q][1]);source[q][mode]=[f,e,int(old_em and e)]
    for k in quotas:
        yields={};cost={}
        for method in next(iter(rows.values()))["priority"]:
            order=sorted(qs,key=lambda q:(-rows[q]["priority"][method],hashkey("ropes-routes-v1/"+q)));selected=set(order[:k])
            yields[method]=np.array([source[q]["new" if q in selected else "old"] for q in qs])
            cost[method]={field:sum(rows[q]["new"][field] for q in selected) for field in ("tokens","calls")}
        comparison={}
        for method in ("basic","random","size","missing"):
            delta=(yields["local"][:,0]-yields[method][:,0])*100
            summed=membership@delta;boot=summed[draws].sum(axis=1)/sizes[draws].sum(axis=1)
            comparison[method]={"delta_pp":float(delta.mean()),"ci95":np.quantile(boot,[.025,.975]).tolist(),
                                "win":int((delta>0).sum()),"loss":int((delta<0).sum())}
        tables[str(k)]={"metric_pct":{m:(v.mean(axis=0)*100).tolist() for m,v in yields.items()},
                        "inc_cost":cost,"local_minus":comparison}
    out={"n":len(qs),"groups":len(groups),"metrics":["F1","EM","both_EM"],"quota":tables,
         "old_forwards":sum(r["old"]["calls"] for r in rows.values()),"new_forwards":sum(r["new"]["calls"] for r in rows.values()),
         "old_tokens":sum(r["old"]["tokens"] for r in rows.values()),"extra_tokens_if_all":sum(r["new"]["tokens"] for r in rows.values()),
         "answer_changed":sum(r["old"]["text"]!=r["new"]["text"] for r in rows.values()),"forecasts":checksum(path)}
    (HERE/"results.json").write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":main()
