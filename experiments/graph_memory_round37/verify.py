"""Validate the released manifests, paired outcomes and key reported quantities offline."""
import gzip
import hashlib
import json
import math
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def read(path):
    p=ROOT/path
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)

def verify():
    release=read("release.json")
    assert len(release["completed"])==len(set(release["completed"])) and set(release["completed"])==set(release["manifests"])
    for study in release["completed"]:
        base=ROOT/study
        manifest=base/"manifest.json"
        assert hashlib.sha256(manifest.read_bytes()).hexdigest()==release["manifests"][study]
        inventory=read(study+"/manifest.json")
        entries=inventory.get("files",inventory)
        for name,record in entries.items():
            p=(base/name).resolve()
            expected=record if isinstance(record,str) else record["sha256"]
            assert p.is_relative_to(base.resolve()) and hashlib.sha256(p.read_bytes()).hexdigest()==expected,p
        assert "REPORT_RU.md" in entries
    policy=read("budget_stopping/test-outcomes.json.gz")
    assert len(policy)==2000 and len({r["t"] for r in policy.values()})==1207
    for arm,fs,harm,tokens in (("full",1623,0,3694815),("learned_5",1522,112,2663963),("matched",1497,137,2656885)):
        assert sum(r["arms"][arm][0] for r in policy.values())==fs
        assert sum(r["arms"][arm][2] for r in policy.values())==tokens
        assert len({r["t"] for r in policy.values() if r["arms"][arm][4]})==harm
    edit=read("code_visibility/predictions.json.gz")
    check=read("editor_baseline/predictions.json.gz")
    assert len(edit)==len(check)==1282 and all(r["mem"]["T"]==check[r["q"]] for r in edit)
    assert sum(len(v) for v in check.values())==28391
    c=read("code_visibility/results.json")["groups"]["main_strict"]
    assert (c["episodes"],c["issues"],c["repos"])==(102,22,5)
    assert (c["methods"]["T"]["correct"],c["methods"]["K"]["wrong"])==(216,7)
    chain=read("edit_chains/results.json")["groups"]["main_strict"]["methods"]
    assert chain["T"]["correct"]==22 and chain["K"]["wrong"]==4
    demand=read("edit_demand/results.json")
    assert demand["n"]==4117 and demand["zones"]["main_clean"]["certified_zero"]==108
    storage=read("code_store/results.json")["totals"]
    assert (storage["A"]["wal_frames"],storage["L"]["wal_frames"])==(2686,4342)
    ranges=read("range_read/forecasts.json.gz")
    assert all(all(y["answer"]==x["arms"]["eager_index"]["answer"] for y in x["arms"].values()) for x in ranges.values())
    assert [sum(r["arms"][k]["returned"] for r in ranges.values()) for k in ("eager_index","inverse","lazy_full")]==[5775,11787,36441]
    guard=read("capacity_guard/results.json")
    assert guard["exact_outputs"]["b4"]==1282 and guard["sqlite_returned"]["exact"]==11403
    ser=read("external_budget/results.json")
    assert ser["n"]==214 and [r["mss"] for r in ser["arms"]["union_cost"]["budget_counts"]][2:5:2]==[69,101]
    native=read("serbench_reference/results.json")
    assert native["successes"]["mmr"][:2]==[73,92] and native["successes"]["union_cost"][:3]==[74,101,69]
    demo=read("read_cost_demo/browser-receipt.json")
    assert demo["threshold_depth_combinations"]==9200 and demo["remote_requests"]==0 and not demo["page_errors"]
    sql=read("observed_sql_demo/checks.json")
    assert sql["ranges"]==709 and len(sql["cases"])==3 and sql["invalid_http_rejected"]==12
    choices=read("plan_choice/results.json")
    assert choices["choices"]["H"]=={"A":71,"L":57}
    plan=read("native_registration/plan.json")
    assert not any(plan["available"][s][a] for s in ("37","41") for a in ("full_rgcn","wo_chunk_adjacency"))
    return len(release["completed"])

if __name__=="__main__":
    print("Verified studies",verify())

