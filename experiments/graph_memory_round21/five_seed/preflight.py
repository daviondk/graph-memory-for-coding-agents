"""Read-only preflight of original model files and randomized samples for the five seeds."""
from collections import Counter
from hashlib import file_digest
from itertools import combinations
from pathlib import Path
import gzip
import json
import shutil
HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
R19=WORK/"graph_memory_round19/trained_rank"
R20=WORK/"graph_memory_round20"
BASE=Path("D:/CodexResearch/x20-isetrace-runtime/e5-base-v2")
PRIVATE=Path("D:/CodexResearch/x20-isetrace-multiseed")
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as s:return file_digest(s,"sha256").hexdigest()
def main():
    seeds=(13,17,29,37,41)
    pos={};neg={};receipts={};counts={}
    for seed in seeds:
        d=R19 if seed==13 else HERE/f"seed-{seed}"
        rows=load(d/"train-pairs.json.gz"); positives=set();negatives=set()
        kinds=Counter()
        for r in rows:
            pair=r["task_id"],r["node_id"];kinds[r["sample_type"]]+=1
            (positives if int(r["label"]) else negatives).add(pair)
        assert len(positives)+len(negatives)<=len(rows) and not positives&negatives
        pos[seed]=positives;neg[seed]=negatives;counts[seed]={"rows":len(rows),"positive":len(positives),"negative":len(negatives),"repeat_rows":len(rows)-len(positives)-len(negatives),"types":dict(kinds)}
        receipts[seed]=sha(d/"train-pairs.json.gz")
    assert all(p==pos[13] for p in pos.values())
    test=load(R19/"split.json.gz");assert {q for q,n in pos[13]}=={r["q"] for r in test["train"]}
    overlap={f"{a}-{b}":[len(neg[a]&neg[b]),len(neg[a]|neg[b])] for a,b in combinations(seeds,2)}
    assert all(0<i<u for i,u in overlap.values())
    files={p.relative_to(BASE).as_posix():sha(p) for p in sorted(BASE.rglob("*")) if p.is_file()}
    expected=load(R19/"weight-audit.json")["base_sha256"];assert files["model.safetensors"]==expected
    observed_bytes=(Path("D:/CodexResearch/x20-isetrace-trained/trained-vectors.sqlite3")).stat().st_size
    sizes=load(HERE/"inputs.json"); projected=int(observed_bytes*sizes["total"]/sizes["test_unique"])
    result={"initial_encoder":files,"base_weights_pinned":expected,"training_pair_shas":receipts,"counts":counts,"negative_intersection_union":overlap,
            "identical_positive_sets":True,"free_D_last_audit":shutil.disk_usage(PRIVATE).free,
            "bytes_estimated_per_seed":{"encoder_checkpoint":(BASE/"model.safetensors").stat().st_size,"embedding_db":projected,
             "basis":"Observed byte size of seed-13 SQLite for 138671 test strings, scaled by new distinct inputs. Excludes transient training and WAL overhead."}}
    target=HERE/"preflight.json"
    if target.exists():
        previous=load(target)
        for k in result.keys()-{"free_D_last_audit"}: assert previous[k]==result[k]
    else:target.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("Same initial encoder and positive labels across five seeds, distinct negatives for each. Expected model plus embeddings about",(projected+(BASE/"model.safetensors").stat().st_size)/2**30,"GiB per seed.")
if __name__=="__main__":main()

