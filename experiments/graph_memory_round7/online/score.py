"""Read sealed predictions and align to the next actually observed explicit editor read."""
import collections
import gzip
import json
import math
import random
from prepare import HERE, digest, dumps, rows, save

def bootstrap(pairs,group_key):
    grouped=collections.defaultdict(lambda:[0,0])
    for row in pairs:
        cell=grouped[row[group_key]]
        cell[0]+=1
        cell[1]+=row["delta"]
    cells=list(grouped.values())
    rnd=random.Random(71321)
    vals=[]
    for _ in range(10000):
        den=0
        num=0
        for n,d in rnd.choices(cells,k=len(cells)):
            den+=n
            num+=d
        vals.append(100*num/den)
    vals.sort()
    return [round(vals[249],4),round(vals[9749],4)]

def summarize(cases,arms,primary=True):
    if not cases:
        return {"n":0}
    n=len(cases)
    stats={arm:{k:sum(v[k][j] for v in cases) for k in ("exact","near","file")} for j,arm in enumerate(arms)}
    comp={}
    for b in ["pooled","recency","graph"]:
        i,j=arms.index("typed"),arms.index(b)
        pairs=[dict(id=q["id"],repo=q["repo"],delta=q["exact"][i]-q["exact"][j]) for q in cases]
        ds=[p["delta"] for p in pairs]
        contrast={"delta_pp":round(100*sum(ds)/n,4),"wins":ds.count(1),"losses":ds.count(-1)}
        if primary and b=="pooled":
            contrast.update(ci95_task_pp=bootstrap(pairs,"id"),ci95_project_pp=bootstrap(pairs,"repo"))
        comp["typed_minus_"+b]=contrast
    return {"n":n,"n_tasks":len({q["id"] for q in cases}),"n_projects":len({q["repo"] for q in cases}),
            "candidate_union_exact":sum(any(v["exact"][:5]) for v in cases),
            "cold":sum(v["context"]=="cold" for v in cases),"scores":stats,"contrasts":comp}

def main():
    lock=json.loads((HERE/"predictions_lock.json").read_bytes())
    assert digest(HERE/"predictions.jsonl.gz")==lock["sha256"] and digest(HERE/"freeze.json")==lock["freeze"]
    frozen=json.loads((HERE/"freeze.json").read_bytes())
    assert all(digest(HERE/k)==v for k,v in frozen["files"].items())
    it=iter(rows(HERE/"predictions.jsonl.gz"))
    all_rows=[]
    compared=0
    arms=lock["arms"]
    with gzip.GzipFile(filename=str(HERE/"scores.jsonl.gz"),mode="wb",mtime=0) as out:
        for episode in rows(HERE/"observations.jsonl.gz"):
            counts=collections.Counter()
            for step,event in enumerate(episode["events"],1):
                iid,t,context,pred=next(it)
                compared+=1
                assert iid==episode["id"] and t==step
                if event is None:
                    continue
                if event[0]=="view":
                    path,page=event[1:3]
                    record=dict(panel=episode["panel"],repo=episode["repo"],id=iid,t=t,context=context,
                                address=[path,page],previous_path_touches=counts[path],
                                exact=[int(x==[path,page]) for x in pred],
                                near=[int(bool(x) and x[0]==path and abs(x[1]-page)<=1) for x in pred],
                                file=[int(bool(x) and x[0]==path) for x in pred])
                    all_rows.append(record)
                    out.write((dumps(record)+"\n").encode())
                counts[event[1]]+=1
    assert next(it,None) is None and compared==lock["rows"]
    summary={}
    for panel in ("claude","kimi"):
        group=[q for q in all_rows if q["panel"]==panel]
        summary[panel]=summarize(group,arms)
        summary[panel]["by_context"]={c:summarize([q for q in group if q["context"]==c],arms,False)
                                     for c in ("cold","view","edit")}
        summary[panel]["by_project"]={repo:summarize([q for q in group if q["repo"]==repo],arms,False)
                                     for repo in sorted({q["repo"] for q in group})}
        summary[panel]["never_observed_file"]=sum(q["previous_path_touches"]==0 for q in group)
    save(HERE/"results.json",summary)
    for panel,s in summary.items():
        print(panel,s["n_tasks"],s["n_projects"],s["n"],s["scores"],s["contrasts"],"after edit",s["by_context"]["edit"]["n"])
if __name__=="__main__":
    main()
