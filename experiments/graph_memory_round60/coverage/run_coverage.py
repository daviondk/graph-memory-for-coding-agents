"""Evaluate graph-coverage representations at the same chronological SQLite prefixes."""
from argparse import ArgumentParser
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import platform
import random
import sqlite3
import sys
from tempfile import TemporaryDirectory

from coverage import R59,Coverage,SketchPolicy,XOR,Hot,possible_losses,varints
from lazy_reader import BlockStore
from run_lazy import GROUPS,source,prepare,identifiers,save,load

HERE=Path(__file__).resolve().parent
R60=HERE.parent
ARMS={"exact":None,"xor":XOR,"lazy":False,"notify":True}
BUDGETS=(1024,4096)
SEED=60061
FROZEN="98bc2b544d6f394c139572b9b4ce1f16da08b204bdb208fa21e284488644fbb2"
NEW_SHA="0e0590566b60acc4b15007c45550c42ee6f6287068c9693609196426555d16fa"


def archives():
    base=R60/"panel"/"events.json.gz"
    assert sha256(base.read_bytes()).hexdigest()==NEW_SHA
    return [(g,source(g)[0]) for g in GROUPS]+[
        ("r59",load(R59/"holdout"/"events.json.gz")),("new",load(base))]


def run_case(path,stream,schedule,seed,baseline):
    ops,fingerprint=prepare(stream,schedule)
    all_ids=iter(identifiers(stream,schedule))
    fence=sum(x[0]=="w" for x in ops)//2
    store=BlockStore(path,"filelist",True)
    readers=None
    gold=defaultdict(list)
    rng=random.Random(seed)
    logs=[]
    max_refs=max_payload=0
    for op in ops:
        if store.next_id==fence and readers is None:
            store.close();store=BlockStore(path,"filelist")
            assert store.next_id==fence and store.restore_rows==store.restore_payload==0
            hot=Hot()
            readers={}
            for cap in BUDGETS:
                for k,policy in ARMS.items():
                    obj=(Coverage(store,hot,cap,policy) if k in ("lazy","notify") else SketchPolicy(store,hot,policy,cap))
                    readers[f"{cap}/{k}"]=obj
        if op[0]=="w":
            _,j,rev,files=op
            assert store.append(j,rev,files)
            for f in files:gold[f].append(j)
            if readers is None:continue
            old=possible_losses(hot,files)
            max_refs=max(max_refs,len(old))
            max_payload=max(max_payload,sum(len(varints((key,)))+len(varints(v)) for key,v in old.items()))
            hot.append(j,files)
            lost=[(key,old[key]) for key in sorted(old) if key not in hot.live]
            for h in readers.values():
                if isinstance(h,Coverage):h.after_committed(j,files,lost)
                else:h.after_write(j,files)
        else:
            t,sha,_=next(all_ids)
            if readers is None:continue
            _,f,tie,prior,expected=op
            out={}
            for label in rng.sample(list(readers),len(readers)):
                h=readers[label]
                if isinstance(h,Coverage):rank,stats=h.read(f,tie,prior,gold[f])
                else:rank,stats=h.read(f,tie,prior)
                assert rank==expected and h.cache.size<=h.cache.limit
                if baseline is not None and not isinstance(h,Coverage):
                    archived=baseline[len(logs)]["arms"][label]
                    assert Counter(stats)==Counter({k:v for k,v in archived.items() if k not in ("resident","read_ns")})
                    assert h.cache.size==archived["resident"]
                out[label]=dict(stats,resident=h.cache.size)
            logs.append(dict(t=t,sha=sha,anchor=f,prefix=store.next_id,arms=out))
    assert next(all_ids,None) is None
    if baseline is not None:assert len(logs)==len(baseline)
    mem={}
    for label,h in readers.items():
        inv=h.cache.inventory()
        if isinstance(h,Coverage):
            inv.update(h.resources)
            if h.notify:
                inv.update(peak_queue=h.cache.peak_queued,peak_queue_payload=h.cache.peak_queue_bytes,
                           peak_hot_candidates=max_refs,peak_hot_candidate_payload=max_payload)
                assert not h.cache.pending
        mem[label]=inv
    store.close()
    return dict(head=stream[-1][0],events=sum(x[0]=="w" for x in ops),fence=fence,oracle=fingerprint,
                logs=logs,memory=mem,source_bytes=path.stat().st_size)


def aggregate(raw):
    groups={}
    for label in (*GROUPS,"r59","new","old12"):
        for p in ("B","long"):
            rows={k:v for k,v in raw.items() if k.split("/")[:2] in [[g,p] for g in (GROUPS if label=="old12" else (label,))]}
            by_arm={};by_project={}
            for k,case in rows.items():
                by_project[k]={}
                for key,mem in case["memory"].items():
                    c=Counter()
                    for r in case["logs"]:
                        c.update({s:n for s,n in r["arms"][key].items() if s!="resident"})
                    c.update(queries=len(case["logs"]),charged=c["posting_bytes"]+c["body_bytes"])
                    c["sql_calls"]=c["body_calls"]+c["posting_calls"]
                    by_project[k][key]=c["charged"]
                    for name in ("exception_insertions","last_copy_lost","maintenance_body_bytes",
                                 "maintenance_packet_bytes_encoded","maintenance_packet_bytes_decoded"):
                        c[name]+=mem.get(name,0)
                    c["sampled_end_python_bytes"]=mem["python"]
                    by_arm.setdefault(key,Counter()).update(c)
            contrast={}
            for budget in BUDGETS:
                for cmp in ("exact","xor","lazy"):
                    a=f"{budget}/notify";b=f"{budget}/{cmp}"
                    vals={k:v[a]-v[b] for k,v in by_project.items()}
                    contrast[f"{budget}/{cmp}"]=dict(delta=sum(vals.values()),win=sum(z<0 for z in vals.values()),
                            tie=sum(z==0 for z in vals.values()),loss=sum(z>0 for z in vals.values()),projects=vals)
            groups[label+"/"+p]=dict(arms=by_arm,charges=by_project,comparisons=contrast)
    return groups


def main():
    parser=ArgumentParser();parser.add_argument("--verify",action="store_true")
    parser.add_argument("--replay",action="store_true",help="Re-run each physical stream and compare its exact counters.")
    args=parser.parse_args();verify=args.verify or args.replay
    assert sha256((HERE/"PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()==FROZEN
    rawpath=HERE/"runs.json.gz";result=HERE/"results.json"
    existing=load(R59/"reconcile"/"runs.json.gz")
    second=load(R59/"holdout"/"queries.json.gz")["sketch"]
    raw=load(rawpath) if rawpath.exists() else dict(protocol=FROZEN,new_source=NEW_SHA,seed=SEED,
                 python=sys.version,sqlite=sqlite3.sqlite_version,system=platform.platform(),cases={})
    assert raw["protocol"]==FROZEN and raw["new_source"]==NEW_SHA
    with TemporaryDirectory(dir=HERE,prefix="coverage-db-") as td:
        for g,streams in archives():
            for repo,stream in streams.items():
                for p in ("B","long"):
                    key="/".join((g,p,repo))
                    known=(existing[g+"-"+p+"/"+repo] if g in GROUPS else second[p+"/"+repo] if g=="r59" else None)
                    if verify:
                        c=raw["cases"][key]
                        assert c["head"]==stream[-1][0]
                        if args.replay:
                            path=Path(td)/"verify.sqlite"
                            measured=run_case(path,stream,p,f"{SEED}/{key}",known)
                            path.unlink();assert not list(Path(td).iterdir())
                            assert measured["logs"]==c["logs"] and measured["oracle"]==c["oracle"]
                            for m,meters in measured["memory"].items():
                                assert {k:v for k,v in meters.items() if k!="python"}=={
                                    k:v for k,v in c["memory"][m].items() if k!="python"}
                        if known is not None:
                            assert len(c["logs"])==len(known)
                            for x,y in zip(c["logs"],known):
                                assert (x["prefix"],x["anchor"])==(y["prefix"],y["anchor"])
                                for cap in BUDGETS:
                                    for kind in ("xor","exact"):
                                        k=f"{cap}/{kind}";z=y["arms"][k]
                                        assert Counter(x["arms"][k])==Counter({t:v for t,v in z.items() if t!="read_ns"})
                    elif key not in raw["cases"]:
                        path=Path(td)/"source.sqlite"
                        case=run_case(path,stream,p,f"{SEED}/{key}",known)
                        path.unlink();assert not list(Path(td).iterdir())
                        raw["cases"][key]=case
                        save(rawpath,raw)
                        print(key,len(case["logs"]),flush=True)
    totals=aggregate(raw["cases"])
    if verify:assert totals==load(result)
    else:save(result,totals)
    print("cases",len(raw["cases"]),"postrestarts",sum(len(c["logs"]) for c in raw["cases"].values()))


if __name__=="__main__":
    main()
