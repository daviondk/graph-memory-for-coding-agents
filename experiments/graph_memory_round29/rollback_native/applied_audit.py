"""Verify the original no-repair transition and apply each frozen structural policy to a private queryable view."""
import sqlite3,os
from collections import defaultdict,Counter
from hashlib import sha256
from pathlib import Path
import numpy as np
from controls import *
def plainhash(data):return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
    db=P/"applied.sqlite"
    sql=sqlite3.connect(db)
    sql.execute("CREATE TABLE IF NOT EXISTS edge_state(panel TEXT, task TEXT, arm TEXT, kind TEXT, ref TEXT, deactivated INTEGER CHECK(deactivated IN(0,1)), PRIMARY KEY(panel,task,arm,kind,ref)) WITHOUT ROWID")
    native=[];summary={}
    for panel in ("controlled","adapted"):
        root=SRC/"data"/("controlled_benchmark" if panel=="controlled" else "adapted_lmev2_subset");reg={r["task_id"]:r for r in readl(root/"registry.jsonl")}
        pred=get(D/(panel+"-forecasts.json.gz"));observed={r["task"]:r for r in get(D/(panel+"-per-case.json.gz"))}
        native_files={}
        for fp in sorted((P/"native"/panel/"outputs").rglob("repaired_result.json")):
            p=get(fp);q=p["case"]["task_id"];assert q not in native_files;native_files[q]=(fp,p)
        sums=Counter();xgroup=defaultdict(list);all_matches=0
        for f in pred:
            q=f["task"];m,t=getcase(root,reg[q]);fp,result=native_files[q]
            rm=readl(fp.parent/result["artifacts"]["repaired_memories"]);rt=readl(fp.parent/result["artifacts"]["repaired_tracesteps"])
            assert rm==m and rt==t
            assert not result["claim_repair"]["applied_invalidated_claim_ids"]
            cost=result["replay_cost"]
            for k,v in cost.items():
                if k in {"llm_call_count","llm_replay_call_count","total_repair_tool_call_count","replayed_target_step_count"}:assert v==0
            native.append(dict(panel=panel,task=q,nmem=len(m),nsteps=len(t),original_memory=plainhash(m),returned_memory=plainhash(rm),original_trace=plainhash(t),returned_trace=plainhash(rt),original_result=sha256(fp.read_bytes()).hexdigest()))
            domain=f["domain"];truth=[r for r in rawfile(root/domain/"ground_truth.jsonl") if r["task_id"]==q][0]
            affected=truth.get("trace_ground_truth",{}).get("affected_steps",truth.get("affected_steps",[]))
            cid={s["step_id"] for s in t if s["step_type"]=="claim"};mid={x["memory_id"] for x in m}
            def step_type_id(z):
                if isinstance(z,str):return z if z in cid else None
                return z.get("faulty_step_id") or z.get("step_id") if z.get("step_type")=="claim" else None
            true={step_type_id(z) for z in affected}-{None};assert true==set(observed[q]["gold_claims"])
            for arm,act in f["policies"].items():
                with sql:
                    # Idempotent replay into our private decisions table; no source rows are mutated.
                    for kind,refs,actions in (("claim",cid,set(act["claims"])),("memory",mid,set(act["mem"]))):
                        assert actions<=refs
                        sql.executemany("INSERT OR IGNORE INTO edge_state VALUES(?,?,?,?,?,0)",((panel,q,arm,kind,v) for v in refs))
                        sql.executemany("UPDATE edge_state SET deactivated=1 WHERE panel=? AND task=? AND arm=? AND kind=? AND ref=?",((panel,q,arm,kind,v) for v in actions))
                        disabled={r[0] for r in sql.execute("SELECT ref FROM edge_state WHERE panel=? AND task=? AND arm=? AND kind=? AND deactivated=1",(panel,q,arm,kind))}
                        assert disabled==actions
                        if kind=="claim":
                            z=observed[q]["arms"][arm];tp=len(true&disabled);fpn=len(disabled-true);fn=len(true-disabled)
                            assert [tp,fpn,fn]==[z[k] for k in ("tp","fp","fn")];xgroup[arm].append((q,tp,fpn,fn))
                sums["applications"]+=1
            all_matches+=1
        res=get(D/(panel+"-results.json"));assert all_matches==res["n"]
        for arm,items in xgroup.items():
            mat=np.array([item[1:] for item in sorted(items)],dtype=int);rng=np.random.default_rng(29029);draw=rng.integers(0,len(mat),(10000,len(mat)));samples=mat[draw].sum(1);tp,fp,fn=samples.T;den=2*tp+fp+fn
            bs=np.divide(2*tp,den,out=np.zeros(len(den)),where=den!=0)
            assert np.allclose(np.percentile(bs,[2.5,97.5]),res["arms"][arm]["ci"],rtol=0,atol=1e-12)
        summary[panel]=dict(noop_identity=all_matches,materialized=sums["applications"],queryable_decision_rows=sql.execute("SELECT count(*) FROM edge_state WHERE panel=?",(panel,)).fetchone()[0])
    trivial=sql.execute("PRAGMA integrity_check").fetchone();assert trivial==("ok",)
    sql.close()
    save(D/"native-receipts.json.gz",native);save(D/"applied-audit.json",dict(panels=summary,db_bytes=db.stat().st_size,db_sha=sha256(db.read_bytes()).hexdigest(),native_receipts=sha256((D/"native-receipts.json.gz").read_bytes()).hexdigest()));print(summary)
if __name__=="__main__":main()

