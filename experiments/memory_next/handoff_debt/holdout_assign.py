"""Open repeated-takeover metadata only. Entire source tasks excluded before fitting policies."""
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from assign import dump
from download import CACHE,pq
from score import ROOT,readrows,result,VIEWS

BASE=VIEWS[:-1]
PREF=["raw_trace","structured_notes","summary_notes","repo_only"]
def choices(train, arms, pred,succ,stage):
    def rate(sub,v, prior=None,n0=0):
        n=len(sub)
        if not n: return prior
        return (sum(result(arms[r[v]],"success") for r in sub)+n0*(prior or 0))/(n+n0)
    def costs(xs,v):
        ts=[result(arms[r[v]],"prompt_tokens") for r in xs]; valid=[n for n in ts if n is not None]
        return mean(valid) if valid else float("inf")
    recv=[r for r in train if r["succ"]==succ]; assert recv
    st=[r for r in recv if r["kind"]==stage]
    combo=[r for r in recv if r["pred"]==pred]
    finest=[r for r in combo if r["kind"]==stage]
    prior={v:rate(recv,v) for v in BASE}
    stage_probs={v:rate(st,v,prior[v],16) for v in BASE}
    costs_={v:costs(recv,v) for v in BASE}
    constant=min(BASE,key=lambda v:(-prior[v],costs_[v],v))
    stage16=min(BASE,key=lambda v:(-stage_probs[v],costs_[v],v))
    lead_probs={}
    for v in BASE:
        pi=rate(train,v)
        for bucket in [recv,combo,finest]:pi=rate(bucket,v,pi,20)
        lead_probs[v]=pi
    lead=max(PREF,key=lambda v:lead_probs[v])
    return dict(receiver=constant,stage16=stage16,lead20=lead),dict(
              n=len(train),recv=len(recv),recv_stage=len(st),pred_recv=len(combo),pred_recv_stage=len(finest),
              p_receiver=prior,p_stage16=stage_probs,p_lead20=lead_probs,train_cost=costs_)

def select():
    cols=["run_id","subset","instance_id","initial_run_id","checkpoint_id","checkpoint_kind","predecessor","successor","handoff_view","attempt"]
    groups=defaultdict(dict)
    for p in sorted(CACHE.glob("*.parquet")):
        for r in pq.read_table(p,columns=cols).to_pylist():
            if r["attempt"] not in ("r02","r03"):continue
            subset,iid,initial,cid,stage,pred,succ=(r[k] for k in cols[1:8])
            key=(subset,iid,initial,cid,stage,pred,succ,r["attempt"])
            assert r["handoff_view"] not in groups[key]
            groups[key][r["handoff_view"]]=r["run_id"]
    assert len(groups)==80 and all(set(g)==set(BASE) for g in groups.values())
    unseen={k[1] for k in groups}; training=[r for r in readrows("assignments.csv") if r["instance"] not in unseen]
    train_ids={r["instance"] for r in training}
    assert unseen.isdisjoint(train_ids) and len(train_ids|unseen)==75
    outcomes={r["run_id"]:r for r in readrows("arm_outcomes.csv")}
    # Expose labels only for train IDs to choices().
    arms={r[v]:outcomes[r[v]] for r in training for v in BASE}
    cache={};stats={};rows=[]
    for key,g in sorted(groups.items()):
        subset,iid,initial,cid,stage,pred,succ,attempt=key
        features=(pred,succ,stage)
        if features not in cache:
            cache[features],stats["/".join(features)]=choices(training,arms,*features)
        rows.append({"instance":iid,"pred":pred,"succ":succ,"stage":stage,"checkpoint":cid,"initial":initial,"attempt":attempt,
                     **cache[features],"manual":"raw_trace" if stage=="post_failed_repair_edit" else "structured_notes",**g})
    dump(ROOT/"heldout_predictions.csv",rows)
    (ROOT/"fit.json").write_text(json.dumps({"train_ids":sorted(train_ids),"test_ids":sorted(unseen),"n_train_pairs":len(training),
            "n_test_pairs":len(rows),"fit":stats},indent=1),encoding="utf-8")
    files=["HELDOUT_PROTOCOL.md","HELDOUT_ADDENDUM.md","lead_protocol.txt","heldout_design_lock.json","heldout_addendum_lock.json",
           "assignments.csv","arm_outcomes.csv","holdout_assign.py","heldout_predictions.csv","fit.json"]
    (ROOT/"heldout_predictions_lock.json").write_text(json.dumps({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},indent=1),encoding="utf-8")
    print(len(train_ids),len(unseen),len(training),len(rows),cache)
if __name__=="__main__":select()

