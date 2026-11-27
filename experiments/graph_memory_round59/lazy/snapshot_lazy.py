"""Matched and generous RAM comparisons between zero-preload and true snapshot + joint."""
import argparse
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import sys
import zlib

from run_lazy import HERE,R58,HORIZONS,GROUPS,References,cases,prepare,save,load
from lazy_reader import BlockStore,Hot,Policy,EVENT,COVER,varints
from checkpoint import BASE,CRC,Demand,make_snapshot,persist,unpack_snapshot

LIMIT=4096


class Protected(Policy):
    def __init__(self,store,hot,cap,blob):
        super().__init__(store,hot,"joint",cap)
        self.raw=blob

    def before(self,f):
        # The protected object has no persistent reverse index in RAM.
        # Temporary query-local decoding trades CPU for an unambiguous persistent-memory cap.
        all_events=unpack_snapshot(self.raw,self.fence,BASE.unpack_from(self.raw)[2])
        return {j:paths for j,paths in all_events.items() if f in paths}

    def covered(self,f):
        return self.cache.get((COVER,f)) is not None

    def certify(self,f,ids,pinned):
        if all(j in pinned for j in ids if j<self.fence):
            self.cache.put((COVER,f),b"")


def get_snapshot(path,store,live,demand,sha,rule,cap):
    padded,n,useful=make_snapshot(live.live,store.next_id,sha,rule,cap,demand)
    envelope=padded[:useful-CRC.size]
    blob=envelope+CRC.pack(zlib.crc32(envelope))
    persist(store.db,blob)
    fence=store.next_id
    store.close()
    store=BlockStore(path,"filelist")
    actual=store.db.execute("SELECT v FROM snapshot WHERE k=1").fetchone()[0]
    raw_sha=store.db.execute("SELECT rev FROM event WHERE j=?",(fence-1,)).fetchone()[0]
    members=unpack_snapshot(actual,store.next_id,raw_sha)
    assert actual==blob and len(members)==n
    return store,actual,members,len(blob)+len(actual)+len(raw_sha)


def replay(path,rows,schedule,original,group,repo,refs):
    ops,_=prepare(rows,schedule)
    writes=[op for op in ops if op[0]=="w"]
    fence=len(writes)//2
    prefix=Hot();demand=Demand()
    store=BlockStore(path,"filelist",True)
    for _,j,sha,files in writes[:fence]:
        assert store.append(j,sha,files)
        prefix.append(j,files);demand.append(files)
    snapshots={}
    for name,rule,cap in (("demand","demand",1024),("full","full",None)):
        store,raw,contents,paid=get_snapshot(path,store,prefix,demand,writes[fence-1][2],rule,cap)
        expected=refs.natural[group][repo]["demand1024" if name=="demand" else name]["paid"]
        assert expected==paid and store.restore_rows==store.restore_payload==0
        snapshots[name]=(raw,contents,paid)
    hot=Hot()
    readers={"baseline":Policy(store,hot,"joint",LIMIT)}
    price={"baseline":0};infeasible=[]
    for name,(blob,contents,paid) in snapshots.items():
        seeded=Policy(store,hot,"joint",LIMIT)
        for j,files in sorted(contents.items()):seeded.cache.put((EVENT,j),varints(files),admission=None)
        readers[name+"-seeded"]=seeded
        price[name+"-seeded"]=paid
        for placement,room in (("bounded",LIMIT-len(blob)),("additional",LIMIT)):
            key=name+"-"+placement
            if room<0:
                infeasible.append(key);continue
            readers[key]=Protected(store,hot,room,blob)
            price[key]=paid
    state={m:dict(limit=h.cache.limit,initial=h.cache.size,
                  pinned=len(h.raw) if isinstance(h,Protected) else 0) for m,h in readers.items()}
    # The archive is the common input. Only the selected mode's state would be live in deployment.
    prefix=demand=snapshots=None
    i=q=0
    trace={m:[] for m in readers}
    for op in ops:
        if op[0]=="w":
            if i>=fence:
                _,j,sha,files=op
                assert store.append(j,sha,files)
                hot.append(j,files)
                for h in readers.values():h.after_write(j,files)
            i+=1
        elif i>=fence:
            _,f,tie,prior,expected=op
            for m,h in readers.items():
                rank,work=h.read(f,tie,prior)
                assert rank==expected
                if m=="baseline":assert work==original[q]
                trace[m].append(work[:5])
            q+=1
    assert q==len(original)
    for m,h in readers.items():
        state[m].update(h.cache.inventory())
        if m.endswith("-bounded"):assert state[m]["peak"]+state[m]["pinned"]<=LIMIT
    store.close()
    return dict(upfront=price,state=state,unavailable=infeasible,reads=trace)


def summary(raw):
    groups=sorted({k.split("/")[0] for k in raw})
    out={}
    for g in [*groups,"external-long","external-B"]:
        keys=[k for k in raw if k.startswith(g+"/") or (g.startswith("external-") and
              k.split("/")[0] in {n+"-"+g.split("-")[1] for n in GROUPS})]
        horizons={}
        for h in HORIZONS:
            metrics={}
            for key in keys:
                obj=raw[key]
                def total(m):
                    ls=obj["reads"][m] if h=="all" else obj["reads"][m][:h]
                    return obj["upfront"][m]+sum(t[2]+t[3] for t in ls)
                base=total("baseline")
                for m in obj["reads"]:
                    diff=total(m)-base
                    report=metrics.setdefault(m,Counter())
                    report.update(cost=total(m),matched_baseline=base,available=1,wins=diff<0,
                                  ties=diff==0,losses=diff>0,upfront=obj["upfront"][m])
            horizons[str(h)]=metrics
        out[g]=horizons
    return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    path=HERE/"snapshot-runs.json.gz";res=HERE/"snapshot-results.json.gz"
    seal=hashlib.sha256((HERE/"SNAPSHOT_PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()
    prior=load(HERE/"runs.json.gz")["cases"];refs=References()
    if verify:
        data=load(path)
        assert seal==data["protocol"] and len(data["cases"])==33 and summary(data["cases"])==load(res)
        for k,c in data["cases"].items():
            assert c["reads"]["baseline"]==[r[:5] for r in prior[k]["reads"]["B8-joint-4096"]]
            group,repo=k.split("/",1)
            for m,charge in c["upfront"].items():
                if m!="baseline":assert charge==refs.natural[group][repo]["demand1024" if m.startswith("demand") else "full"]["paid"]
        print("Verified matched and generous control outcomes for 33 schedules.");return
    data=load(path) if path.exists() else dict(protocol=seal,cases={})
    assert seal==data["protocol"]
    with TemporaryDirectory(dir=HERE,prefix="combined-") as folder:
        for g,repo,schedule,stream in cases():
            key=g+"/"+repo
            if key in data["cases"]:continue
            db=Path(folder)/"one.sqlite"
            data["cases"][key]=replay(db,stream,schedule,prior[key]["reads"]["B8-joint-4096"],g,repo,refs)
            db.unlink()
            assert not list(Path(folder).iterdir())
            save(path,data)
            print(key,flush=True)
    save(res,summary(data["cases"]))


if __name__=="__main__":
    main()
