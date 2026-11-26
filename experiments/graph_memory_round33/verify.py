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

    one=read("budget_loss/test-outcomes.json.gz")
    rest={}
    for sh in range(8):
        part=read(f"budget_loss/transfer-outcomes-{sh}.json.gz")
        assert rest.keys().isdisjoint(part)
        rest.update(part)
    assert len(one)==2000 and one.keys()==rest.keys()
    assert len({r["t"] for r in one.values()})==1207
    totals={a:0 for a in ("frozen","point_0.3","cost_worst_0.03")}
    for q,r in one.items():
        assert r["t"]==rest[q]["t"] and set(rest[q]["seeds"])=={"17","29","37","41"}
        for record in [r["arms"],*rest[q]["seeds"].values()]:
            for method in totals:totals[method]+=int(record[method][0])
    assert totals=={"frozen":7960,"point_0.3":7965,"cost_worst_0.03":8046},totals
    factorial=read("graph_ablation/test-outcomes.json.gz")
    assert set(factorial)==set(one)
    assert sum(r["arms"]["metadata.cost_worst_0.03"][0] for r in factorial.values())==1495
    for q,r in factorial.items():
        assert r["arms"]["graph.cost_worst_0.03"]==one[q]["arms"]["cost_worst_0.03"]
    storage=read("precision/lossless-rows.json.gz")
    assert len(storage)==2000 and sum(v[0]==0 for r in storage.values() for v in r.values())==9960
    states=read("incremental_percentiles/equivalence.json")
    assert states["states"]==364 and states["question_states"]==514 and states["sums"]["edges_revoked"]==126
    mus=read("musique_answers/matched-outcomes.json.gz")
    assert len(mus)==2417 and len({r["cluster"] for r in read("musique_answers/outcomes.json.gz").values()})==1734
    assert all(r["local_static"][1]==r["mention_title"][1] and len({v[2] for v in r.values()})==1 for r in mus.values())
    assert math.isclose(sum(r["local_static"][1]-r["title"][1] for r in mus.values())/len(mus),.019853402072699102)
    assert set(release["completed"])==set(release["manifests"])
    return len(release["completed"])

if __name__=="__main__":print("Verified studies",verify())
