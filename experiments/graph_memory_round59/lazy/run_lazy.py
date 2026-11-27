"""Replay all demand-only cache readers and align the natural checkpoint charges at every horizon."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import platform
import sqlite3
import sys
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
from lazy_reader import ARM, FIELDS, BlockStore, Hot, Policy, footprint
R58=HERE.parents[1]/"graph_memory_round58"
sys.path.insert(0,str(R58/"restart_transfer"))
from run_transfer import source, prepare, load, save, identifiers, GROUPS
from bench_restart import panels

HORIZONS=(0,1,4,16,"all")
REFS={"snapshot-full":"full","snapshot-demand1024":"demand1024"}
PRIMARY=("B8-joint-4096","B8-events-4096","B8-counts-4096")
ALL=(*ARM,*REFS)


def cases():
    for p in ("B","long"):
        for r,rows in panels()[p].items():
            yield "original-"+p,r,p,rows
    for g in GROUPS:
        data,_=source(g)
        for r,rows in data.items():
            for p in ("B","long"):yield g+"-"+p,r,p,rows


class References:
    def __init__(self):
        main=load(R58/"restart"/"runs.json.gz")["runs"]
        self.original={(r["panel"],r["project"],r["method"]):r["queries"] for r in main if r["rep"]==0}
        self.external=load(R58/"restart_transfer"/"runs.json.gz")["projects"]
        self.natural=load(R58/"restart_transfer"/"no-padding.json")["projects"]

    def get(self,group,repo,p,name):
        data=self.natural[group][repo][name]
        if group.startswith("original-"):
            raw=[[q[0],*q[2:]] for q in self.original[p,repo,name]]
        else:
            g=group.split("-")[0]
            raw=self.external[g+"/"+repo]["workloads"][p]["arms"][name]["work"]
        # Retain returned payload, number of SQL calls and event rows.
        costs=[[q[1],q[2],q[3],q[5],q[4]] for q in raw if q[0]]
        assert data["charged"]==data["paid"]+sum(r[2]+r[3] for r in costs)
        return costs,data["paid"]


def evaluate(path,group,repo,p,stream,refs):
    ops,digest=prepare(stream,p)
    keys=iter(identifiers(stream,p))
    total=sum(op[0]=="w" for op in ops)
    fence=total//2
    end_points={1,max(1,(total-fence)//2),total-fence}
    store=BlockStore(path,"filelist",create=True)
    logs={m:[] for m in ARM}
    inventories=[]
    reader=None
    idx=0
    ids=[]
    for op in ops:
        if idx==fence and reader is None:
            store.close();store=BlockStore(path,"filelist")
            assert store.next_id==fence and not store.restore_rows and not store.restore_payload
            assert store.db.execute("PRAGMA synchronous").fetchone()==(2,)
            hot=Hot()
            reader={m:Policy(store,hot if w else None,k,b) for m,(k,w,b) in ARM.items()}
        if op[0]=="w":
            _,j,rev,files=op
            assert store.append(j,rev,files)
            idx+=1
            if reader:
                hot.append(j,files)
                for h in reader.values():h.after_write(j,files)
                if idx-fence in end_points:inventories.append(inventory(hot,reader,idx))
        else:
            ident=next(keys)
            if reader:
                _,f,tie,prior,expected=op
                ids.append([ident[0],ident[1],f])
                for m,h in reader.items():
                    rank,work=h.read(f,tie,prior)
                    assert rank==expected,(group,repo,ident,m,rank,expected)
                    logs[m].append(work)
    assert next(keys,None) is None and store.next_id==total
    inventories.append(inventory(hot,reader,idx))
    assert store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
    store.close()
    size=path.stat().st_size
    raw_cold,paid=refs.get(group,repo,p,"cold")
    assert paid==0 and [r[:5] for r in logs["B8"]]==raw_cold
    paid={m:0 for m in ARM}
    for m,from_arm in REFS.items():
        costs,price=refs.get(group,repo,p,from_arm)
        assert len(costs)==len(ids)
        logs[m]=costs
        paid[m]=price
    return dict(git_head=stream[-1][0],commits=len(stream),events=total,fence=fence,oracle=digest,
                ids=ids,reads=logs,upfront=paid,samples=inventories,database_bytes=size)


def inventory(hot,readers,idx):
    known=readers["B8"].known
    assert all(r.known==known for r in readers.values() if r.hot is not None)
    return dict(event_count=idx,common_python=footprint((hot,known)),common_hot_estimate=hot.budget(),
                arms={m:r.cache.inventory() for m,r in readers.items()})


def totals(cases):
    groups={}
    names=sorted({g.split("/")[0] for g in cases})
    for group in [*names,"external-B","external-long"]:
        if group.startswith("external"):
            p=group.split("-")[1]
            parts={k:v for k,v in cases.items() if k.split("/")[0] in {g+"-"+p for g in GROUPS}}
        else:
            parts={k:v for k,v in cases.items() if k.startswith(group+"/")}
        horizon={}
        for h in HORIZONS:
            per={};group_sum={m:Counter() for m in ALL}
            for key,case in parts.items():
                project={}
                for m in ALL:
                    selected=case["reads"][m] if h=="all" else case["reads"][m][:h]
                    totals=Counter(queries=len(selected),upfront=case["upfront"][m])
                    for row in selected:
                        totals.update(dict(zip(FIELDS[:-1],row[:-1])) if m in ARM else dict(zip(FIELDS[:5],row)))
                    totals["charged"]=totals["upfront"]+totals["posting_bytes"]+totals["body_bytes"]
                    totals["calls"]=totals["posting_calls"]+totals["body_calls"]
                    group_sum[m].update(totals)
                    project[m]=totals["charged"]
                per[key]=project
            contrasts={}
            for control in [*PRIMARY[1:],"B8","B8-postings-4096","snapshot-full","snapshot-demand1024"]:
                deltas={key:z[PRIMARY[0]]-z[control] for key,z in per.items()}
                contrasts[control]=dict(deltas=deltas,wins=sum(v<0 for v in deltas.values()),
                                        losses=sum(v>0 for v in deltas.values()),ties=sum(v==0 for v in deltas.values()))
            horizon[str(h)]=dict(arms=group_sum,contrast=contrasts,per_project=per)
        groups[group]=horizon
    return groups


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    path=HERE/"runs.json.gz"
    digest=hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()
    if verify:
        raw=load(path)
        assert raw["protocol"]==digest and len(raw["cases"])==33
        assert totals(raw["cases"])==load(HERE/"results.json.gz")
        refs=References()
        for key,case in raw["cases"].items():
            g,repo=key.split("/",1);p=g.split("-")[1]
            rows,paid=refs.get(g,repo,p,"cold")
            assert paid==0 and [r[:5] for r in case["reads"]["B8"]]==rows
            for m,arm in REFS.items():
                baseline,fixed=refs.get(g,repo,p,arm)
                assert case["reads"][m]==baseline and case["upfront"][m]==fixed
        print("Verified summaries, R58 per-query baseline parity and checkpoint references.");return
    raw=load(path) if path.exists() else dict(protocol=digest,fields=FIELDS,python=sys.version,
                    platform=platform.platform(),sqlite=sqlite3.sqlite_version,cases={})
    assert raw["protocol"]==digest
    refs=References()
    with TemporaryDirectory(dir=HERE,prefix="lazy-store-") as folder:
        for g,repo,p,stream in cases():
            key=g+"/"+repo
            if key in raw["cases"]:continue
            db=Path(folder)/"one.sqlite"
            case=evaluate(db,g,repo,p,stream,refs)
            db.unlink()
            assert not list(Path(folder).iterdir())
            raw["cases"][key]=case
            save(path,raw)
            print(key,len(case["ids"]),flush=True)
    save(HERE/"results.json.gz",totals(raw["cases"]))


if __name__=="__main__":
    main()
