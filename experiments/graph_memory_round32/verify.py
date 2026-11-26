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
    a=read("isetrace_five_seeds/per-query.json.gz");rows=a["rows"];ix=a["metrics"].index("full_support_2048")
    assert len(rows)==len({(r[0],r[1]) for r in rows})==10000
    assert len({r[2] for r in rows})==1207
    assert [sum(r[j][ix] for r in rows) for j in [3,4]]==[7297,7844]
    assert read("seed_stability/results.json")["all_five_win"]==72
    for folder,n,n2 in [("observed_transfer",12576,9825),("musique_links",2417,1252)]:
        data=read(folder+"/outcomes.json.gz");two=[r for r in data.values() if r["g"]==2]
        assert len(data)==n and len(two)==n2
        indep=read("reader_audit/audit.json")[folder]["counts"]
        for m in two[0]["hits"]:
            assert sum(r["hits"][m]==2 for r in two)==indep[m]["both"]
    cases=read("representative_tree/cases.json.gz")
    assert len(cases)==7405 and sum(r["events"] for r in cases.values())==412168
    decisions=read("early_read/actions.json.gz")
    for ds,rec in decisions.items():
        for row in rec.values():
            full=row["full"]
            for m in ("cert16","cert32","cert64"):
                assert full[0]==row[m][0] and row[m][1]<=full[1]
    assert read("code_handoff_demo/verified.json")["native_queries"]==342
    assert set(release["completed"])==set(release["manifests"])
    return len(release["completed"])
if __name__=="__main__":print("Verified studies",verify())
