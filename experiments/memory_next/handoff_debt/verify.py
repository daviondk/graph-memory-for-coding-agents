"""Verify the frozen cohort and reproduce the tested lookup rule from all 6,120 compact run rows."""
import hashlib
import json
from score import ROOT,compute,readrows
from heldout_score import compute as heldout_score
from heldout_diagnostics import run as heldout_diagnostics
from cost_controls import run as cost_controls

def verify():
    allfiles=ROOT/"MANIFEST.sha256"
    if allfiles.exists():
        for line in allfiles.read_text(encoding="utf-8").splitlines():
            h,n=line.split("  ",1);assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    locks=json.loads((ROOT/"blind_lock.json").read_text(encoding="utf-8"))
    for n,h in locks.items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    assignments=readrows("assignments.csv");source=readrows("arm_outcomes.csv")
    ids=[r[a] for r in assignments for a in ("raw_trace","structured_notes","summary_notes","repo_only")]
    assert len(ids)==len(set(ids))==6120 and set(ids)=={r["run_id"] for r in source}
    assert len({r["instance"] for r in assignments})==75
    assert len({(r["instance"],r["initial"],r["checkpoint"]) for r in assignments})==510
    assert sum(r["policy"]=="raw_trace" for r in assignments)==255
    assert compute()==json.loads((ROOT/"results.json").read_text(encoding="utf-8"))
    got={r["instance"] for r in assignments if r["instance"].startswith(("psf__requests-","pallets__flask-"))}
    assert got=={"psf__requests-2931","psf__requests-6028"}
    for n,h in json.loads((ROOT/"heldout_predictions_lock.json").read_text(encoding="utf-8")).items():
        assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    fit=json.loads((ROOT/"fit.json").read_text(encoding="utf-8"))
    test=readrows("heldout_predictions.csv"); obs=readrows("heldout_outcomes.csv")
    trainids=set(fit["train_ids"]); testids=set(fit["test_ids"])
    assert len(trainids)==53 and len(testids)==22 and trainids.isdisjoint(testids)
    assert {r["instance"] for r in test}==testids and len(test)==80
    assert {r[a] for r in test for a in ["raw_trace","structured_notes","summary_notes","repo_only"]}=={r["run_id"] for r in obs}
    for r in test:
        vals=fit["fit"]["/".join((r["pred"],r["succ"],r["stage"]))]
        assert r["lead20"]==max(["raw_trace","structured_notes","summary_notes","repo_only"],key=lambda a:vals["p_lead20"][a])
        assert r["stage16"]==min(vals["p_stage16"],key=lambda a:(-vals["p_stage16"][a],vals["train_cost"][a],a))
    assert heldout_score()==json.loads((ROOT/"heldout_results.json").read_text(encoding="utf-8"))
    assert heldout_diagnostics()==json.loads((ROOT/"heldout_diagnostics.json").read_text(encoding="utf-8"))
    assert cost_controls()==json.loads((ROOT/"heldout_cost_controls.json").read_text(encoding="utf-8"))
    print("OK: 6,120 r01 arms, 1,530 frozen choices, 75 task clusters; 320 held-out arms, 53/22 train/test source IDs, both frozen policies, paired costs and clustered bootstrap")

if __name__=="__main__":verify()

