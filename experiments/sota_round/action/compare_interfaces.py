"""Pair the separately frozen JSON and plain-Python interfaces by task and arm."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from analyze_action import estimate, lines


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("json_study",type=Path)
    cli.add_argument("plain_study",type=Path)
    args=cli.parse_args()
    first,second=args.json_study,args.plain_study
    assert (first/"assigned.jsonl").read_bytes()==(second/"assigned.jsonl").read_bytes()
    a=lines(first/"requests.jsonl")
    b=lines(second/"requests.jsonl")
    assert len(a)==len(b)==102
    for old,new in zip(a,b):
        assert old["id"]==new["id"]
        d=json.loads(old["prompt"][old["prompt"].index('{"issue":'):])
        e=json.loads(new["prompt"][new["prompt"].index('{"issue":'):])
        for key in ("issue","existing_files","memory"):
            assert d[key]==e[key]
    def load(p):
        with (p/"action_per_cell.csv").open(encoding="utf-8",newline="") as f:
            return {r["id"]:r for r in csv.DictReader(f)}
    json_cells,plain_cells=load(first),load(second)
    comparisons={}
    for arm in ("raw","receipt","empty"):
        pairs=[dict(task=r["task"], original=r["ok"]=="True", plain=plain_cells[k]["ok"]=="True")
               for k,r in json_cells.items() if r["arm"]==arm]
        comparisons[arm]=estimate(pairs,"plain","original")
    res=dict(n_tasks=34,cell_pairs=102,unchanged_payload_fields=["issue","existing_files","memory"],
             assignment_sha256=hashlib.sha256((first/"assigned.jsonl").read_bytes()).hexdigest(),
             plain_minus_json_by_arm=comparisons)
    (second/"interface_comparison.json").write_text(json.dumps(res,indent=2)+"\n",encoding="utf-8")
    print({k:(v["wins"],v["losses"]) for k,v in comparisons.items()})


if __name__=="__main__":
    main()
