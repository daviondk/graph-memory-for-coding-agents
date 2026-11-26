"""Capacity-matched suffix refills registered before the first external SQL replay."""
import argparse
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from generate import HERE,read,save,sha
import replay
from classic import ClassicStore
from partial import PartialStore
from reserve_store import ReserveStore
PLANS=("lazy8","classic8","partial8","partial12")

def extended(db,name,create):
    if name=="lazy8":return ReserveStore(db,8,"lazy",create=create)
    if name=="classic8":return ClassicStore(db,8,create=create)
    if name in ("partial8","partial12"):return PartialStore(db,int(name[7:]),create=create)
    raise ValueError(name)

def main(verify,scratch):
    for receipt in ("stream-seal.json","policy-seal.json","extension-seal.json"):
        assert all(sha(HERE/k)==v for k,v in read(receipt).items()),receipt
    streams=read("streams.json.gz");refs=read("snapshot-oracle.json.gz");raw={};results={}
    with TemporaryDirectory(dir=scratch) as tmp,patch.object(replay,"method",extended):
        for schedule in ("once","restart25"):
            raw[schedule]={};results[schedule]={}
            for plan in PLANS:
                costs={};checks={}
                for q,rows in streams.items():
                    path=Path(tmp)/(schedule+plan+q.replace("/","_")+".sqlite")
                    costs[q],checks[q]=replay.run(path,q,rows,refs[q],plan,schedule=="restart25")
                raw[schedule][plan]=costs
                outcome=dict(per_repo=checks,base=replay.total([ev[0] for ev in costs.values()]),
                    steady=replay.total([x for ev in costs.values() for x in ev[1:]]),
                    graph_changed=replay.total([costs[q][j] for q in streams for j,row in enumerate(streams[q]) if j and (row["delta"] or row["born"])]))
                results[schedule][plan]=outcome
                print(schedule,plan,outcome["steady"],flush=True)
    primary=read("results.json")
    first=read("event-costs.json.gz")["events"]
    schedule_identity={}
    index=replay.COLUMNS.index("warm_probes")
    for schedule in results:
        schedule_identity[schedule]={}
        for n in (8,12):
            full=(raw if n==8 else first)[schedule][f"lazy{n}"]
            partial=raw[schedule][f"partial{n}"]
            schedule_identity[schedule][f"lazy{n}/partial{n}"]=sum(
                a[index]!=b[index] for q in full for a,b in zip(full[q],partial[q],strict=True))
        for checks in results[schedule].values():
            for q,r in checks["per_repo"].items():
                ref=primary["schedules"][schedule]["lazy12"]["per_repo"][q]
                assert (r["packet_hash"],r["end_db_bytes"])==(ref["packet_hash"],ref["end_db_bytes"])
    save("extension-costs.json.gz",dict(columns=replay.COLUMNS,events=raw),verify)
    save("extension-results.json",dict(sqlite=sqlite3.sqlite_version,schedules=results,warm_schedule_disagreements=schedule_identity),verify)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--register",action="store_true")
    parser.add_argument("--verify",action="store_true");parser.add_argument("--scratch",type=Path,default=HERE)
    args=parser.parse_args()
    if args.register:
        assert not (HERE/"results.json").exists() and not (HERE/"extension-results.json").exists()
        pins=["EXTENSION_RU.md","extension.py","policy-seal.json","../reserve/partial.py"]
        save("extension-seal.json",{p:sha(HERE/p) for p in pins})
    else:main(args.verify,args.scratch)
