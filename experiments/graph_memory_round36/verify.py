"""Validate released study files and headline quantities using the measured rows."""
import gzip,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(path):
    p=ROOT/path;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def verify():
    release=read("release.json")
    for name,wanted in release["manifests"].items():
        base=ROOT/name
        p=next(p for p in (base/"manifest.json",base/"MANIFEST_SHA256.json") if p.is_file())
        sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
        assert sha(p)==wanted,p
        content=json.loads(p.read_bytes());files=content.get("files",content)
        if isinstance(files,list):files={f.get("name",f.get("file")):f.get("sha",f.get("sha256")) for f in files}
        assert set(files)=={f.relative_to(base).as_posix() for f in base.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f!=p}
        for rel,expected in files.items():
            file=(base/rel).resolve();dig=expected["sha256"] if isinstance(expected,dict) else expected
            assert file.is_relative_to(base) and sha(file)==dig,file

    states=read("materialized_append/outcomes.json.gz")
    assert len(states)==len({(r["q"],r["cut"]) for r in states})==8000
    cohort={r["q"] for r in states if r["cut"]==50 and r["eligible"] and not r["pilot"]}
    assert len(cohort)==901
    counts={k:sum(r["arms"][k][0] for r in states if r["cut"]==50 and r["q"] in cohort) for k in ("E","M","L")}
    assert counts=={"E":752,"M":742,"L":725}
    random=read("edge_count_control/outcomes.json.gz")
    assert sum(random[q]["arms"][f"G_s{i:02d}"][0] for q in cohort for i in range(8))==5937
    assert all(random[q]["arms"][f"T_s{i:02d}"][:2]==random[q]["arms"]["M"][:2] for q in cohort for i in range(8))
    graphs={}
    for i in range(8):graphs.update(read(f"materialized_append/graphs-{i}.json.gz"))
    assert len(graphs)==1207
    assert [sum(r["states"]["50"][k] for r in graphs.values()) for k in ("exact","material","logical")]==[35568,40336,102488]
    sensitivity=read("trajectory_sensitivity/histories.json.gz")
    assert set(sensitivity)==set(graphs)
    assert sum(r["never"] for r in sensitivity.values())==62152
    stream=read("streaming_witnesses/results.json")["totals"]
    assert stream["steps"]==72186 and stream["checked_cuts"]==4828 and stream["terminal_open"]==0
    assert read("temporal_semantics/enumeration.json")["snapshot_cases"]==57344
    assert read("visibility_join/results.json")["primary_cuts"]==512
    assert read("unannotated_traces/results.json")["native_pairset_hash_checks"]==792
    assert read("history_demo/browser-receipt.json")["edge_checks"]==108
    multi=read("multiseed_midpoint/outcomes.json.gz")
    assert set(multi)=={r["q"] for r in states}
    assert [sum(multi[q]["seeds"][s][m][0] for q in cohort for s in ("17","29","37","41")) for m in ("M","L","E","E35")]==[2958,2872,2992,3000]
    train_seeds=[read(f"native_three_seeds/four-arms-{seed}.json.gz") for seed in (13,17,29)]
    assert all(row.keys()==set(multi) for row in train_seeds)
    assert [sum(v[j][0] for seed in train_seeds for v in seed.values()) for j in (1,2,3,4)]==[4860,4831,4717,4731]
    for study in ("deferred_match","indexed_arguments","multiseed_density"):
        assert (ROOT/study/"REPORT_RU.md").is_file()
    assert set(release["completed"])==set(release["manifests"])
    return len(release["completed"])

if __name__=="__main__":print("Verified studies",verify())
