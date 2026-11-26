"""Verify the local evidence and reconstruct every five-seed summary from question-level outcomes."""
from pathlib import Path
import gzip, hashlib, json, math
from collections import defaultdict

ROOT=Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(name):
    path=ROOT/name
    if path.suffix==".gz":
        with gzip.open(path,"rt",encoding="utf8") as stream:return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))

def close(a,b):
    return math.isclose(a,b,abs_tol=1e-11)

def main():
    manifest=read("manifest.json")
    for k,h in manifest.items():assert digest(ROOT/k)==h,k
    assert set(manifest)=={p.name for p in ROOT.iterdir() if p.is_file() and p.name!="manifest.json"}
    for stage in ("dev","test"):
        s=read(stage+"-seal.json")
        for k,n in (("rank",stage+"-ranks.json.gz"),("protocol","PROTOCOL_RU.md"),("script","frontier.py")):
            assert s[k]==digest(ROOT/n),n
    selection=read("selection.json"); assert not set(selection["cal_t"])&set(selection["hold_t"])
    assert len(selection["cal_t"])==len(selection["hold_t"])==176
    assert selection["cal_questions"]==286
    r=read("results.json")
    assert r["panels"]["test"]["t"]==1207
    assert r["panels"]["test"]["n"]==2000
    for panel in r["panels"].values(): assert panel["non_nested_transitions"]["single_prefix"]==0
    assert read("count-selection.json")["k"]==2
    rs=read("repeat-seal.json"); gs=read("guard-seal.json"); gr=read("guard-results.json")
    assert rs["script"]==digest(ROOT/"transfer.py") and gs["script"]==digest(ROOT/"guard.py")
    for k,v in rs["parts"].items(): assert digest(ROOT/k)==v,k
    assert gs["assignments"]==digest(ROOT/"guard-assignments.json.gz")
    decisions=read("guard-assignments.json.gz"); pooled=defaultdict(lambda:[0.]*9); seen=set(); tids=set()
    for i in range(8):
        f=f"repeat-outcomes-{i}.json.gz"
        assert gr["score_inputs"][f]==digest(ROOT/f)
        part=read(f)
        for q,row in part.items():
            assert q not in seen; seen.add(q); tids.add(row["t"])
            assert set(row["seeds"])=={"13","17","29","37","41"}
            for seed,arms in row["seeds"].items():
                for m,scores in {**arms,**{k:arms[v] for k,v in decisions[q][seed].items()}}.items():
                    assert all(0<=v<=1 for v in scores) and close(scores[0],sum(scores[1:6])/5)
                    for j,v in enumerate(scores):pooled[m][j]+=v
    assert seen==decisions.keys() and len(seen)==2000 and len(tids)==1207
    expected={**read("repeat-results.json")["stats"]["all5"]["means"],**gr["panels"]["all5"]["means"]}
    for m,a in expected.items():
        assert all(close(v/10000,w) for v,w in zip(pooled[m],a)),m
    assert read("floor.json")["test"]==digest(ROOT/"test-outcomes.json.gz")
    print(f"{len(manifest)} files; 2000 questions, 1207 trajectories, 5 seeds, {len(expected)} policies re-aggregated")
if __name__=="__main__":main()
