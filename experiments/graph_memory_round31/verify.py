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
    measured=read("support_pairs/cache-measurements.json.gz")
    reported=read("support_pairs/results.json")["cache"]["joint"]["2"]
    for method in ("tree","raw","linear","previous_plus_raw"):
        rows=[v["joint"]["2"]["stats"][method][1][2] for v in measured.values()]
        totals=[sum(r[i] for r in rows) for i in (0,1)]
        assert totals==[reported[method]["events_at_f"],reported[method]["exact_events"]]
    assert len(measured)==7405 and reported["tree"]["exact_events"]==331063
    timed=read("pair_store/timing.json.gz")
    assert len(timed)==40320 and len({(r[0],r[1]) for r in timed})==1152
    assert all(len({r[-1] for r in group})==1 for group in by_event(timed).values())
    links=read("observed_links/outcomes.json.gz")
    published=read("observed_links/results.json")["panels"]
    for mode,panel in [("sparse","sparse"),("dense","dense_512")]:
        members=[v[mode] for v in links.values() if mode in v]
        for method,stats in published[panel]["methods"].items():
            assert stats["both"]==sum(v["exact"][method] for v in members)
    demo=read("pair_demo/verification.json")
    assert demo["masks"]==24576 and demo["raw_fallback_up_to_two"]==127
    assert set(release["completed"])==set(release["manifests"])
    return len(release["completed"])
def by_event(rows):
    from collections import defaultdict
    groups=defaultdict(list)
    for r in rows:groups[r[0],r[1]].append(r)
    return groups
if __name__=="__main__":print("Verified studies",verify())
