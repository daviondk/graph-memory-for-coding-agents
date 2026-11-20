"""Score the prelocked planner using independent, freshly executed node outcomes."""
from common import *
from collections import Counter, defaultdict
from random import Random
import zipfile

def stats(rows):
    n=len(rows)
    c=Counter(x["source"] for x in rows)
    answered=[r for r in rows if r["answer"] in ("passed","failed")]
    acc=sum(r["correct"] for r in answered)
    return dict(n=n,confirmed=c["confirm"],predicted=c["historical_prediction"],abstained=c["abstain"],
                answered=len(answered),correct=acc,wrong=len(answered)-acc,
                false_pass=sum(r["answer"]=="passed" and r["truth"]=="failed" for r in answered),
                false_failure=sum(r["answer"]=="failed" and r["truth"]=="passed" for r in answered),
                correct_per_query=acc/n,coverage=len(answered)/n,conditional_accuracy=acc/len(answered) if answered else None)

def contrast(rows,pa,pb):
    zipped=defaultdict(dict)
    for r in rows:
        if r["policy"] in (pa,pb):zipped[r["key"],r["node"]][r["policy"]]=int(r["correct"])
    by_task=defaultdict(list)
    for (k,node), v in zipped.items():
        by_task[k.split("/")[1]].append(v[pa]-v[pb])
    blocks=[(sum(v),len(v)) for k,v in sorted(by_task.items())]
    rng=Random(1019);samples=[]
    for _ in range(10000):
        replicate=rng.choices(blocks,k=len(blocks));samples.append(sum(x[0] for x in replicate)/sum(x[1] for x in replicate))
    samples.sort()
    def quant(q):
        t=(len(samples)-1)*q;i=int(t)
        return samples[i]+(samples[min(i+1,len(samples)-1)]-samples[i])*(t-i)
    return dict(issues=len(blocks), gain=sum(d==1 for v in by_task.values() for d in v),
                loss=sum(d==-1 for v in by_task.values() for d in v),counts_by_issue={k:[sum(v),len(v)] for k,v in by_task.items()},
                delta=sum(x[0] for x in blocks)/sum(x[1] for x in blocks),ci95=[quant(.025),quant(.975)])

def cost_totals(batch):
    result=Counter(queries=1,pages=batch["pages"],page_bytes=batch["page_bytes"],blob_bytes=batch["blob_bytes"],
            tokens=batch["tokens"],rendered_utf8_bytes=len(batch["rendered"].encode()))
    result["states_"+batch["state"]]+=1
    return result

def main():
    il=get(ROOT/"input-lock.json");pl=get(ROOT/"plan-lock.json");fl=get(ROOT/"fresh-lock.json")
    for data in (pl["code"],fl["files"],fl["runners"]):
        for name,h in data.items():assert fh(ROOT/name)==h
    for name,h in il["sources"].items():assert fh(WORK/name)==h
    assert il["prior_code"]==fh(R9/"budget/sketch.py")
    assert fh(ROOT/"inputs.gz")==il["inputs"]==pl["inputs"]
    assert fh(ROOT/"plans.gz")==fl["plans"]==pl["plans"]
    assert fh(ROOT/"history.gz")==pl["history"] and fh(ROOT/"fresh-results.gz")==fl["data"]
    rset=get(ROOT/"inputs.gz");hist={v["key"]:v for v in get(ROOT/"history.gz")}
    current={v["key"]:{x["node"]:x for x in v["receipts"]} for v in get(ROOT/"current.gz")}
    fresh=get(ROOT/"fresh-results.gz");rows=[]; disagreements=[]; known={};checks=Counter()
    cost=defaultdict(Counter);size=Counter();addresses={};historical_cost={};current_cost={};packet_cost={}
    for r in rset:
        k=r["key"];h=hist[k];dirno=sha(k.encode())[:16]
        past={v["node"]:v for v in h["answers"]};assert len(past)==len(r["items"])
        prior_r9=get(PANELS[r["panel"]]/"runs"/r["task"]/("gold.json.gz" if r["direction"]=="fix" else "base.json.gz"))
        checks["invalidated"]+=h["invalidated"]
        snapshot=ROOT/"native"/(dirno+".zip");assert fh(snapshot)==h["native_snapshot_sha"]
        for item in r["items"]:
            node=item["node"];new=fresh[k][node];saved=current[k][node]; prev=past[node]
            checks["old_exact_matching"]+=prev["before"]==item["prior"]
            checks["historical_matching"]+=prev["historical"]==item["prior"]
            checks["historical_marked"]+=prev["marked_historical"]
            checks["pre_confirm_current_returned"]+=prev["current_before"] is not None
            checks["new_confirm_current_matching"]+=saved["status"]==new["status"]
            assert new["status"] in ("passed","failed") and saved["status"]==new["status"]
            o=status(prior_r9["reports"],node)
            if o!=new["status"]:disagreements.append([k,node,o,new["status"]])
            checks["queries"]+=1
            checks["changed_status"]+=prev["historical"]!=new["status"]
            known[k,node]=r["task"],r["panel"],new["status"],saved["status"]
        d={}
        with zipfile.ZipFile(snapshot) as z:
            for name in z.namelist():
                if not name.endswith(".page.json"):continue
                pg=json.loads(z.read(name))
                fact=pg["groups"][0]["events"][0]["facts"][0]
                entity=fact["key"]["canonical_entity_id"].removeprefix("test:");page=pg["manifest"]["page_id"]
                d[entity]=page
        addresses[k]=d
        size["common_directory_pageid_uncompressed_json"]+=len(packed({n:d[n] for n in past}))
        for mode in ("fixed","selected"):
            name="suite-observation/"+mode
            size["directory_extra_"+mode]+=len(packed({**{n:d[n] for n in past},name:d[name]}))-len(packed({n:d[n] for n in past}))
            size["raw_dependency_bytes_"+mode]+=r["packets"][mode]["bytes"]
            size["base64_ascii_bytes_"+mode]+=len(r["packets"][mode]["data"])
        for name in ("bytes_at_test_checkpoint_including_wal","closed_archive_logical_bytes","zip_size"):size[name]+=h[name]
        for stage in ("history","current"):
            for rec in get(ROOT/"native"/(dirno+"-"+stage+".gz")):
                q,n=rec["query"],rec["node"];ct=cost_totals(rec)
                cost[q].update(ct)
                if q=="new_after_run":current_cost[k,n]=ct
                if q=="old_from_new":historical_cost[k,n]=ct
                if q.startswith("sketch_"):packet_cost[k,q.removeprefix("sketch_")]=ct
                if q=="old_from_new" or q.startswith("sketch_"):
                    entity=n if n else "suite-observation/"+q.removeprefix("sketch_")
                    frame=json.loads("\n".join(rec["rendered"].splitlines()[2:-1]))
                    assert frame["memory_ref"]=="memoryref_"+sha(d[entity].encode())[:24]
    put(ROOT/"addresses.gz",addresses)
    policy_cost=defaultdict(Counter)
    for p in get(ROOT/"plans.gz"):
        k,n,src,pol=p["key"],p["node"],p["source"],p["policy"]; task,panel,gold,new=known[k,n]
        if pol in ("strict","fixed","selected","unchecked","carry_all"):policy_cost[pol].update(historical_cost[k,n])
        if src=="confirm":policy_cost[pol].update(current_cost[k,n])
        result=new if src=="confirm" else p["historical"] if src=="historical_prediction" else None
        rows.append({**p,"task":task,"panel":panel,"truth":gold,"answer":result,"correct":result==gold})
    for (k,pol),v in packet_cost.items():policy_cost[pol].update(v)
    panels={v["panel"] for v in rows};methods=sorted({v["policy"] for v in rows})
    scores={};contrasts={}
    for panel in ["both",*sorted(panels)]:
        group=[v for v in rows if panel=="both" or v["panel"]==panel]
        scores[panel]={p:stats([v for v in group if v["policy"]==p]) for p in methods}
        contrasts[panel]={b:contrast(group,"selected",b) for b in ("fixed","strict","unchecked")}
    put(ROOT/"outcomes.gz",rows);put(ROOT/"results.json",dict(scores=scores,contrasts_selected_minus=contrasts))
    put(ROOT/"costs.json",dict(native_queries=cost,reader_by_policy=policy_cost,storage=size))
    put(ROOT/"verification.json",dict(checks=checks,num_source_files=len(il["sources"]),num_fresh_files=len(fl["files"]),r9_disagreements=disagreements,
                    results={s:fh(ROOT/s) for s in ("score.py","current.gz","outcomes.gz","results.json","costs.json","addresses.gz")}))
    print(json.dumps(scores["both"]));print(json.dumps(contrasts["both"]["fixed"]));print(checks,disagreements)
if __name__=="__main__":main()
