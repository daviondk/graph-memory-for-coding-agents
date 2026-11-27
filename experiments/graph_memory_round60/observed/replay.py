"""Exact event-graph retrieval replay at editor-window coordinates (no text)."""
import argparse
from collections import Counter, defaultdict, deque
from contextlib import closing
from hashlib import sha1, sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
R59=EXP/"graph_memory_round59"
ARCHIVE=EXP/"graph_memory_round57/agent_trace/prefixes.json.gz"
sys.path.insert(0,str(R59/"reconcile"))
from bench_sketch import BlockStore, Hot, Policy, SketchPolicy, XOR, NUM, load, save
from lazy_reader import FIELDS

CAPS=(256,1024,4096)
BLOCKS=(16,4)
MODES=("events","joint","exact","count","xor")


def coordinates():
    out=[]
    for t in load(ARCHIVE):
        windows=[]
        empty=0
        for event in t["events"]:
            if len(event)!=3:
                continue
            _,path,lines=event
            nums=tuple(sorted({line[0] for line in lines}))
            if not nums:
                empty+=1
                continue
            assert nums[0]>=1
            windows.append((path,nums))
        out.append(dict(repo=t["repo"],issue=t["issue"],actor=t["actor"],windows=windows,empty=empty))
    return out


def readers(db):
    hot=Hot()
    policies={}
    for cap in CAPS:
        for name in MODES:
            if name in ("joint","events"):
                model=Policy(db,hot,name,cap)
            else:
                kind={"count":NUM,"xor":XOR,"exact":None}[name]
                model=SketchPolicy(db,hot,kind,cap)
            policies[cap,name]=model
    return hot,policies


def query_truth(history,anchor,ids,freq):
    relevant=[event for event in history if anchor in event]
    counts=Counter(x for event in relevant for x in event)
    candidates=(x for x in ids.values() if x!=anchor)
    ranks=sorted(candidates,key=lambda x:(-counts[x],-freq[x],x))[:8]
    prior=sorted(ids.values(),key=lambda x:(-freq[x],x))[:9]
    return [(x,counts[x]) for x in ranks],prior,len(relevant)


def source_revision(t,n,m):
    # An identifier of this observed window, not a Git commit or source generation.
    return sha1(f"window/{t['issue']}/{t['actor']}/{n}/{m}".encode()).hexdigest()


def publish(hot,arms,j,assigned):
    hot.append(j,assigned)
    for h in arms.values():
        h.after_write(j,assigned)
        assert h.cache.size<=h.cache.limit


def run(dbpath,t,span,readers_factory=readers,apply_write=publish):
    mid=len(t["windows"])//2
    history=[]
    ids={}
    seen_anchors=set()
    used_this_process=set()
    freq=Counter()
    recent=deque()
    logs=[]
    db=BlockStore(dbpath,"filelist",True)
    try:
        for wi,(path,nums) in enumerate(t["windows"]):
            if wi==mid:
                db.close()
                db=BlockStore(dbpath,"filelist")
                hot,arms=readers_factory(db)
                assert db.next_id==len(history)
            blocks=tuple(sorted({(number-1)//span for number in nums}))
            addresses=tuple((path,b) for b in blocks)
            anchor=ids.get(addresses[0],-1)
            if wi>=mid:
                expected,prior,pcount=query_truth(history,anchor,ids,freq)
                row=dict(window=wi,anchor=anchor,anchor_known=anchor!=-1,anchor_seen=addresses[0] in seen_anchors,
                         anchor_repeat=addresses[0] in used_this_process,posting_n=pcount,rank=expected,arms={})
                for (cap,name),h in arms.items():
                    got,stats=h.read(anchor,freq,prior)
                    assert got==expected, (t["issue"],wi,cap,name,got,expected)
                    assert h.cache.size<=cap
                    if isinstance(stats,list):
                        stats=dict(zip(FIELDS,stats))
                    row["arms"][f"{cap}/{name}"]={k:v for k,v in stats.items() if v and k!="cache_size"}
                used_this_process.add(addresses[0])
                logs.append(row)
            assigned=tuple(ids.setdefault(a,len(ids)) for a in addresses)
            if len(recent)==32:
                freq.subtract(recent.popleft())
            recent.append(assigned)
            freq.update(assigned)
            if 2<=len(assigned)<=64:
                j=len(history)
                history.append(assigned)
                assert db.append(j,source_revision(t,wi,span),assigned)
                if wi>=mid:
                    apply_write(hot,arms,j,assigned)
            seen_anchors.add(addresses[0])
    finally:
        db.close()
    if t["windows"]:
        for h in arms.values():
            h.cache.inventory()
    return dict(repo=t["repo"],issue=t["issue"],actor=t["actor"],empty=t["empty"],windows=len(t["windows"]),
                cut=mid,graph_events=len(history),nodes=len(ids),rows=logs)


def charge(v):
    return v.get("posting_bytes",0)+v.get("body_bytes",0)


def condition(row,tag):
    if tag=="repeat":
        return row["anchor_repeat"]
    if tag=="supported":
        return row["posting_n"]>=4
    return True


def metric_stats(sessions,cap=None):
    distribution=Counter()
    posting=Counter()
    total=defaultdict(Counter)
    sessions_with_repeat=sessions_with_support=0
    for s in sessions:
        repeated=False
        supported=False
        for row in s["rows"]:
            distribution.update(queries=1,known=row["anchor_known"],anchor_seen=row["anchor_seen"],
                                repeat=row["anchor_repeat"],supported=row["posting_n"]>=4)
            posting[row["posting_n"]]+=1
            repeated |= row["anchor_repeat"]
            supported |= row["posting_n"]>=4
            for a,v in row["arms"].items():
                if cap is None or a.startswith(str(cap)+"/"):
                    total[a].update(v)
        sessions_with_repeat+=repeated
        sessions_with_support+=supported
    for v in total.values():
        v["charged"]=charge(v)
    return dict(arms={k:dict(v) for k,v in total.items()},distribution=dict(distribution),
                posting_hist={str(k):v for k,v in sorted(posting.items())},sessions_with_repeat=sessions_with_repeat,
                sessions_with_support=sessions_with_support)


def contrasts(sessions,cap,subset="all"):
    issue=Counter()
    cs=Counter()
    win=tie=loss=0
    costs_equal=0
    nqueries=0
    for s in sessions:
        ds=[]
        for r in s["rows"]:
            if not condition(r,subset):
                continue
            a=charge(r["arms"][f"{cap}/xor"])
            b=charge(r["arms"][f"{cap}/exact"])
            cs.update(xor=a,exact=b)
            costs_equal+=a==b
            nqueries+=1
            ds.append(a-b)
        d=sum(ds)
        issue[s["issue"]]+=d
        win+=d<0
        tie+=d==0
        loss+=d>0
    y=np.array(list(issue.values()),dtype=np.int64)
    rng=np.random.default_rng(60031)
    m=rng.multinomial(len(y),np.ones(len(y))/len(y),size=20000)
    lo,hi=np.quantile(m@y/len(y),[.025,.975])
    return dict(nqueries=nqueries,queries_equal=costs_equal,xor=cs["xor"],exact=cs["exact"],delta=int(y.sum()),
                sessions_wtl=[win,tie,loss],issues_wtl=[int((y<0).sum()),int((y==0).sum()),int((y>0).sum())],
                mean_issue=float(y.mean()),ci95_mean=[float(lo),float(hi)])


def summary(raw):
    out={}
    for span,ss in raw.items():
        by_repo={p:[s for s in ss if s["repo"]==p] for p in sorted({s["repo"] for s in ss})}
        by_actor={p:[s for s in ss if s["actor"]==p] for p in sorted({s["actor"] for s in ss})}
        x=metric_stats(ss)
        x.update(sessions=len(ss),issues=len({s["issue"] for s in ss}),windows=sum(s["windows"] for s in ss),
                 empty=sum(s["empty"] for s in ss),events=sum(s["graph_events"] for s in ss),
                 contrasts={f"{c}/{subset}":contrasts(ss,c,subset) for c in CAPS for subset in ("all","repeat","supported")},
                 repos={p:contrasts(t,1024) for p,t in by_repo.items()},actors={p:contrasts(t,1024) for p,t in by_actor.items()})
        out[span]=x
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    traces=coordinates()
    assert len(traces)==108 and len({s["issue"] for s in traces})==54
    archive=HERE/"queries.json.gz"
    with TemporaryDirectory(dir=HERE) as tmp:
        raw={}
        for span in BLOCKS:
            ss=[]
            for tr in traces:
                path=Path(tmp)/"memory.sqlite"
                ss.append(run(path,tr,span))
                path.unlink()
                assert not list(Path(tmp).iterdir())
            raw[str(span)]=ss
    result=dict(source_sha256=sha256(ARCHIVE.read_bytes()).hexdigest(),
               protocol_sha256_lf=sha256((HERE/"PROTOCOL_RU.md").read_text(encoding="utf8").encode()).hexdigest(),
               spans=summary(raw))
    for p,v in ((archive,raw),(HERE/"results.json",result)):
        if args.verify:
            # JSON uses lists for pair records.
            import json
            assert json.loads(json.dumps(v))==load(p)
        else:
            save(p,v)
    for span,x in result["spans"].items():
        print(span,x["distribution"],x["contrasts"]["1024/all"],flush=True)


if __name__=="__main__":
    main()
