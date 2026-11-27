"""Place a short certificate only when the current resident set can use it."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from bench_sketch import BlockStore, HERE, LIMITS, cases, load, prepare, save, simulate
from lazy_reader import entry_size
from summary_cache import SketchPolicy, XOR, NUM, POST, EVENT, encode, full


class Governed(SketchPolicy):
    def __init__(self,store,hot,mode,cap):
        super().__init__(store,hot,XOR,cap)
        self.mode=mode

    def recover(self,record,present):
        ids,diff=super().recover(record,present)
        if self.mode=="disabled" and diff==1:return None,diff
        return ids,diff

    def admit(self,f,ids,record,stats):
        compact=encode(ids,XOR)
        if compact[0]!=XOR or self.mode=="disabled":return compact
        if self.mode=="sticky" and record is not None and (record[0]<NUM or stats["failed"]):
            stats["held_full"]+=1
            return full(ids)
        hot=self.hot.incident.get(f,())
        cached={j for j in ids if j not in hot and (EVENT,j) in self.cache.items}
        missing=sum(j not in hot and j not in cached for j in ids)
        key=(POST,f)
        charge=entry_size(key,compact)
        before=self.cache.items.get(key)
        excess=self.cache.size+charge-(entry_size(key,before) if before is not None else 0)-self.cache.limit
        if missing<=1 and excess>0:
            for old,blob in self.cache.items.items():
                if old==key:continue
                excess-=entry_size(old,blob)
                if old[0]==EVENT and old[1] in cached:missing+=1
                if excess<=0 or missing>1:break
        stats["declined" if missing>1 else "accepted"]+=1
        return full(ids) if missing>1 else compact


def factory(store,hot):
    modes={}
    for cap in LIMITS:
        modes[cap,"exact"]=SketchPolicy(store,hot,None,cap)
        modes[cap,"xor"]=SketchPolicy(store,hot,XOR,cap)
        for policy in ("gate","sticky","disabled"):
            modes[cap,policy]=Governed(store,hot,policy,cap)
    return modes


def run():
    hold=load(HERE.parent/"holdout/events.json.gz")
    inputs=list(cases())+[("holdout-"+p,n,p,h) for n,h in hold.items() for p in ("long","B")]
    raw={}
    with TemporaryDirectory(dir=HERE) as temp:
        path=Path(temp)/"store.sqlite"
        for group,repo,p,stream in inputs:
            ops,_=prepare(stream,p)
            with closing(BlockStore(path,"filelist",True)) as db:
                raw[group+"/"+repo]=simulate(db,ops,factory)
            path.unlink()
    return raw


def summarize(raw):
    groups={}; projects={}
    for key,rows in raw.items():
        prefix=key.split("/",1)[0]
        g=groups.setdefault(prefix,{})
        projects[key]={}
        for cap in LIMITS:
            for m in ("exact","xor","gate","sticky","disabled"):
                name=f"{cap}/{m}"
                s=Counter()
                for r in rows:s.update({k:v for k,v in r["arms"][name].items() if k!="resident"})
                s.update(queries=len(rows),charged=s["body_bytes"]+s["posting_bytes"])
                projects[key][name]=s["charged"]
                g.setdefault(name,Counter()).update(s)
    return dict(groups=groups,projects=projects)


if __name__=="__main__":
    ap=ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    name=HERE/"admission-runs.json.gz"
    raw=load(name) if args.verify else run()
    result=summarize(raw)
    if args.verify:assert result==load(HERE/"admission-results.json")
    else:save(name,raw);save(HERE/"admission-results.json",result)
    for g,arms in result["groups"].items():print(g,[arms["1024/"+m]["charged"] for m in ("exact","xor","gate","sticky","disabled")])
