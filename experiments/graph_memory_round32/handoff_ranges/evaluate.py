"""Evaluate route and materialization separately for fixed successor reads."""
from collections import defaultdict
from statistics import mean
import numpy as np
from handoff import D,PRIOR,sha,get,save,METHODS
FIELDS=("boundary_pair","boundary_recall","interior_pair","interior_recall","route","address_wp","read_wp","total_wp")
def analyze(rows):
    by=defaultdict(list)
    for r in rows:by[r["issue"]].append(r)
    issues=sorted(by);draw=np.random.default_rng(32031).integers(len(issues),size=(10000,len(issues)))
    means={k:np.array([np.mean([z["arms"][k] for z in by[i]],axis=0) for i in issues]) for k in rows[0]["arms"]}
    contrasts={}
    for a,b in [("one_wide/boundary","one_wide/forward"),("novel/boundary","one_wide/boundary"),("one_wide/boundary","last/boundary"),("one_wide/boundary","full/boundary")]:
        dif=means[a]-means[b];ci=np.quantile(dif[draw].mean(axis=1),[.025,.975],axis=0)
        contrasts[a+" vs "+b]={k:dict(diff=dif[:,j].mean(),interval=ci[:,j].tolist(),wins=int((dif[:,j]>1e-12).sum()),losses=int((dif[:,j]<-1e-12).sum())) for j,k in enumerate(FIELDS)}
    return dict(issues=issues,n=len(rows),sums={m:sum(r["arms"][m][0] for r in rows) for m in means},means={k:dict(zip(FIELDS,x.mean(axis=0).tolist())) for k,x in means.items()},contrasts=contrasts)
def main():
    lock=get(D/"seal.json");glock=get(D/"reference-seal.json");assert sha(D/"packets.json.gz")==lock["packets"]==glock["inputs"] and sha(D/"targets.json.gz")==glock["targets"]
    r31=get(PRIOR/"results.json");assert sha(PRIOR/"fixed-outcomes.json.gz")==r31["fixed_receipt"]
    packets=get(D/"packets.json.gz");gold=get(D/"targets.json.gz");fixed=get(PRIOR/"fixed-outcomes.json.gz")
    meta={r["group"]:r for r in get(PRIOR/"delivery-metadata.json.gz") if r["view"]=="repo_only"};split=get(D/"split.json")
    rows=[]
    for r in fixed:
        g=r["group"];m=meta[g];assert g==m["group"] and r["cp"]==m["cp"];cp=m["cp"];p=packets[cp];t=gold[m["q"]]
        issue=r["issue"];outputs={};ends=list(map(tuple,t["ends"]));inner=list(map(tuple,t["inner"]))
        for a in METHODS:
            idx=p["routes"].get(t["path"],{}).get(a);address=p["address_tokens"][a]
            for s in ("forward","boundary"):
                body=p["material"][str(idx)][s] if idx is not None else {"tokens":0,"keys":[]}
                seen=set(map(tuple,body["keys"]));e=[v in seen for v in ends];i=[v in seen for v in inner]
                assert a=="full" or address<=512
                assert body["tokens"]<=512 and (not all(e) or r["available_pair"])
                outputs[a+"/"+s]=[int(all(e)),mean(e),int(all(i)),mean(i),int(idx is not None),address,body["tokens"],address+body["tokens"]]
        rows.append(dict(group=g,cp=cp,issue=issue,scope=r["subset"],split="dev" if issue in split["dev"] else "test",available=r["available_pair"],n=t["n"],distinct_quartiles=(not(set(ends)&set(inner))),arms=outputs))
    summary={}
    for scope in sorted({r["scope"] for r in rows}):
        for split in ("dev","test","all"):
            selected=[r for r in rows if r["scope"]==scope and (split=="all" or r["split"]==split)]
            if not selected:continue
            summary[scope+"/"+split]=analyze(selected)
            if scope=="main_takeovers" and split=="test":
                strict=[r for r in selected if r["distinct_quartiles"]]
                if strict:summary["main_takeovers/test-interior-distinct"]=analyze(strict)
    save(D/"results.json",{"fields":FIELDS,"groups":summary,"outcomes":save(D/"outcomes.json.gz",rows),"historic_serialized_bytes_across_snapshots":sum(p["raw_bytes"] for p in packets.values()),"checkpoint_event_copies":sum(p["unique_events"] for p in packets.values())})
if __name__=="__main__":main()