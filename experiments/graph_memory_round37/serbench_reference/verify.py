"""Offline verification with standard library; no model runtime or label data required."""
from pathlib import Path
from hashlib import sha256
from collections import Counter
import argparse,gzip,json,math
D=Path(__file__).resolve().parent
FILES=("PROTOCOL_RU.md","REPORT_RU.md","REPRODUCE_RU.md","availability.json","common.py","sources.py",
       "mmr.py","rerank.py","freeze.py","grade.py","verify.py","mmr-dev.json","mmr-predictions.json.gz",
       "reranker-scores.json.gz","seal.json","predictions.json.gz","outcomes.json.gz","results.json")
def digest(path):return sha256(path.read_bytes()).hexdigest()
def load(name):
    b=(D/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def main(seal):
    old=load("seal.json")
    assert all(digest(D/key)==value for key,value in old["files"].items())
    src=load("availability.json")
    assert len(src["reference"])==12 and all(x["file"] in src["tree"] for x in src["reference"].values())
    r=load("results.json");o=load("outcomes.json.gz");p=load("predictions.json.gz")
    raw=load("reranker-scores.json.gz");mmr=load("mmr-predictions.json.gz")
    assert o.keys()==p.keys()==raw.keys()==mmr.keys() and len(o)==r["states"]==214
    assert set(r["successes"])=={"mmr","dense_state","bm25","cross_encoder","union_cost"}
    assert r["repos"]==len({row["repo"] for row in o.values()})==69
    assert sum(map(len,raw.values()))==6848
    for sid, methods in p.items():
        for key,ids in methods.items():
            assert len(ids)==len(set(ids))==8
            scores=o[sid]["scores"][key];assert set(scores)<={0,1}
            assert scores[0]<=scores[1] and scores[2]<=scores[3]<=scores[1] and scores[4]<=scores[1]
            cut=o[sid]["cuts"][key];assert 0<=cut[0]<=cut[1]<=8 and 0<=cut[2]<=8
        assert sorted(row[0] for row in raw[sid])==list(range(32)) and len({row[1] for row in raw[sid]})==32
        assert all(math.isfinite(row[2]) for row in raw[sid])
    for key,t in r["successes"].items():
        assert t==[sum(x["scores"][key][j] for x in o.values()) for j in range(5)]
    for contrast,c in r["comparisons"].items():
        a,b=contrast.split(" minus ")
        for j in range(5):
            diffs=[v["scores"][a][j]-v["scores"][b][j] for v in o.values()]
            assert diffs.count(1)==c["won"][j] and diffs.count(-1)==c["lost"][j]
            assert abs(sum(diffs)/len(diffs)-c["delta"][j])<1e-12
    dev=load("mmr-dev.json");assert float(max(dev["counts"],key=lambda k:(dev["counts"][k],float(k))))==dev["selected"]==.75
    checksums={name:digest(D/name) for name in FILES}
    path=D/"manifest.json"
    if seal:path.write_text(json.dumps(checksums,sort_keys=True,indent=2),encoding="utf-8")
    assert checksums==load("manifest.json")
    print("OK",len(FILES),"files;",len(o),"states; manifest",digest(path))
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--seal",action="store_true")
    main(parser.parse_args().seal)
