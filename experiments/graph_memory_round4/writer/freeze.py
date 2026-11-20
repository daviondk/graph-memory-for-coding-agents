"""Choose one method on open development B, then freeze the only untouched C panel."""
from datetime import datetime,timezone
from shared import D,A,B,R3,read,save,sha,prior
from memory import CANDIDATES,CONTROLS

def main():
    dest=D/"freeze.json"
    assert not dest.exists() and not (D/"panel_C/checkpoint_lock.json").exists()
    a=read(D/"panel_A/results.json");b=read(D/"panel_B/results.json")
    def score(k):
        return (b["arms"][k]["full"],a["arms"][k]["full"],-b["operation_cost"][k]["mean_ms"])
    candidate=max(CANDIDATES,key=score)
    codec=["dict_lru","dict_mixed"] if candidate!="plain_neighbor" else ["lru","mixed"]
    best=max(codec,key=score)
    refs=list(dict.fromkeys(["lru","point","typed","mixed","dict_lru","dict_mixed","dict_center","cal_pages","cal_center",candidate]))
    inputs=[D/f for f in ("PROTOCOL_RU.md","choose_roster.py","acquire_data.py","dictionary.py","python_prior.bin","risk.py","risk_model.json","memory.py","experiment.py","shared.py","audit_controls.py","controls_audit.json","freeze.py","selection.json","receipts.json","panel_A/results.json","panel_B/results.json")]
    inputs.extend([*sorted(D.glob("source_*.jsonl.gz")),B/"writer_followup.py",B/"transfer_followup.py",A/"acquire.py",
        R3/"context/context.py",prior.R2/"span_memory/run.py",prior.R2/"span_memory/width_model.json",prior.R2/"span_memory/offset.json",prior.R2/"edit_memory/model.json"])
    save(dest,dict(utc=datetime.now(timezone.utc).isoformat(),candidate=candidate,comparison_same_codec=best,arms=refs,
                   rankings={k:score(k) for k in CANDIDATES},inputs={str(p):sha(p) for p in inputs}))
    print(candidate,best,refs)
if __name__=="__main__":main()
