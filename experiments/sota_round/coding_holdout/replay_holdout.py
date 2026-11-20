"""Recompute all three ordered responses and compare with the recorded blind runs."""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from predict_holdout import ROOT, infer


def replay(task):
    q = task["instance_id"]
    expected = json.loads((ROOT/"predictions"/(q+".json")).read_bytes())
    actual = infer(task)
    for key in ("instance_id","repo","base_commit","chunks","chunk_inventory_sha256","query_names_count","tfidf","prior","new"):
        assert actual[key] == expected[key], (q,key)
    return q


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--workers",type=int,default=4)
    args=p.parse_args()
    tasks=json.loads((ROOT/"tasks.json").read_bytes())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        checked=list(pool.map(replay,tasks))
    assert len(checked)==len(set(checked))==30
    print("Recomputed all 30 ordered inventories and 90 ordered top-five lists; exact match.")
