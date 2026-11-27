"""Real loopback read and update costs, measured on identical committed SQLite prefixes."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import platform
from random import Random
from shutil import copyfile
import sqlite3
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"coverage"))
from run_coverage import Coverage,SketchPolicy,XOR,Hot,BlockStore,possible_losses,load,save,prepare,NEW_SHA
sys.path.insert(0,str(HERE.parents[1]/"graph_memory_round59"/"transport"))
from wire import service
from rank_rpc import rank_service

SEED=60079
FROZEN="fcaadb1efadb35d13babff359715ff4eb86d8c0f0d69fa6f2986374840a32351"
MODES=[(cap,mode,lag) for cap in (1024,4096) for mode in ("exact","xor","notify") for lag in (0,2)]
MODES.extend((0,"server",lag) for lag in (0,2))


def run(dbpath,ops,log,cap,mode,lag):
    server_rank=mode=="server"
    init=perf_counter_ns()
    reads=[];writes=[];payload=Counter();digest=sha256()
    with closing(BlockStore(dbpath,"filelist")) as writer:
        with (rank_service(dbpath,lag) if server_rank else service(dbpath,lag)) as endpoint:
            rpc,remote,wait=endpoint[:3]
            hot=None if server_rank else Hot()
            proxy=SimpleNamespace(db=rpc,next_id=writer.next_id)
            reader=(None if server_rank else Coverage(proxy,hot,cap,True) if mode=="notify"
                    else SketchPolicy(proxy,hot,XOR if mode=="xor" else None,cap))
            started=perf_counter_ns()
            for o in ops:
                if o[0]=="w":
                    _,j,sha,files=o
                    mark=perf_counter_ns()
                    assert writer.append(j,sha,files)
                    write_ns=perf_counter_ns()-mark
                    discovery_ns=hot_ns=cache_ns=0
                    if reader is not None:
                        mark=perf_counter_ns()
                        previous=possible_losses(hot,files) if mode=="notify" else {}
                        discovery_ns=perf_counter_ns()-mark if mode=="notify" else 0
                        mark=perf_counter_ns();hot.append(j,files);hot_ns=perf_counter_ns()-mark
                        proxy.next_id=writer.next_id
                        mark=perf_counter_ns()
                        if mode=="notify":
                            lost=[(idx,previous[idx]) for idx in sorted(previous) if idx not in hot.live]
                            reader.after_committed(j,files,lost)
                        else:reader.after_write(j,files)
                        cache_ns=perf_counter_ns()-mark
                    writes.append([j,write_ns,discovery_ns,hot_ns,cache_ns])
                    continue
                _,f,tie,prior,expected=o
                prev=rpc.ledger.counts.copy()
                mark=perf_counter_ns()
                if server_rank:
                    rank,(request,reply,floor)=rpc.rank(f,tie)
                else:
                    rank,s=reader.read(f,tie,prior)
                ns=perf_counter_ns()-mark
                assert rank==expected
                digest.update((json.dumps(rank,separators=(",",":"))+"\n").encode())
                idx=len(reads)
                assert log[idx]["anchor"]==f and log[idx]["prefix"]==writer.next_id
                if server_rank:
                    reads.append([writer.next_id,f,ns,request,reply,1,floor])
                else:
                    stats=rpc.ledger.counts-prev
                    target=log[idx]["arms"][f"{cap}/{mode}"]
                    for col in ("posting_bytes","body_bytes","posting_calls","body_calls"):
                        assert s[col]==target.get(col,0)
                    assert s["posting_calls"]==stats["posting_calls"] and s["body_calls"]==stats["bodies_calls"]
                    request=stats["posting_req_bytes"]+stats["bodies_req_bytes"]
                    reply=stats["posting_resp_bytes"]+stats["bodies_resp_bytes"]
                    reads.append([writer.next_id,f,ns,request,reply,s["posting_calls"]+s["body_calls"],0,
                                 s["posting_bytes"],s["body_bytes"],stats["posting_req_bytes"],stats["posting_resp_bytes"],
                                 stats["bodies_req_bytes"],stats["bodies_resp_bytes"]])
                    payload.update(posting_bytes=s["posting_bytes"],body_bytes=s["body_bytes"])
            stop=perf_counter_ns()
            seal=rpc.ledger.seal()
        assert remote.seal()==seal
        if server_rank:
            source=endpoint[3];tx,rx,_=seal
            payload.update(source)
        else:tx,rx=seal["request_sha"],seal["response_sha"]
    assert len(reads)==len(log)
    return dict(reads=reads,writes=writes,setup_ns=started-init,wall_ns=stop-started,
                sleep_ns=wait["actual_emulated_sleep_ns"],req_sha=tx,res_sha=rx,rank_sha=digest.hexdigest(),sql=payload)


def summarize(data):
    by={};projects={}
    for key,z in data.items():
        block,org,repo,cb,mode,lag=key.split("/")
        arm=f"{cb}/{mode}/{lag}";project=org+"/"+repo
        tot=Counter(n=len(z["reads"]),writes=len(z["writes"]),wall_ns=z["wall_ns"],setup_ns=z["setup_ns"],sleep_ns=z["sleep_ns"])
        for row in z["reads"]:
            tot.update(read_ns=row[2],request=row[3],reply=row[4],wire=row[3]+row[4],trips=row[5],
                       shared_prior_lower=row[6]+row[4] if mode=="server" else 0)
        for j,src,detect,hot,updates in z["writes"]:
            tot.update(source_ns=src,detect_ns=detect,hot_ns=hot,updates_ns=updates)
        tot.update(z["sql"])
        by.setdefault(arm,{}).setdefault(block,Counter()).update(tot)
        if block=="0" and lag=="0":projects.setdefault(project,{})[f"{cb}/{mode}"]=dict(
            wire=tot["wire"],trips=tot["trips"],request=tot["request"],reply=tot["reply"],n=tot["n"])
    summary={}
    for arm,block in by.items():
        a=[block[str(i)] for i in range(3)]
        assert all(k.endswith("_ns") or len({r[k] for r in a})==1 for k in a[0])
        summary[arm]=dict(counters={k:v for k,v in a[0].items() if not k.endswith("_ns")},
            measured={k:dict(median=median(r[k] for r in a),blocks=[r[k] for r in a])
                      for k in a[0] if k.endswith("_ns")})
    return dict(arms=summary,projects=projects)


def main():
    ap=ArgumentParser();ap.add_argument("--verify",action="store_true");verify=ap.parse_args().verify
    src=HERE.parent/"panel"/"events.json.gz"
    assert sha256(src.read_bytes()).hexdigest()==NEW_SHA
    assert sha256((HERE/"PROTOCOL_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()==FROZEN
    rawp=HERE/"runs.json.gz";resp=HERE/"results.json"
    stored=load(rawp) if rawp.exists() else dict(protocol=FROZEN,source_sha=NEW_SHA,seed=SEED,python=sys.version,
                       platform=platform.platform(),sqlite=sqlite3.sqlite_version,runs={})
    assert stored["protocol"]==FROZEN and stored["source_sha"]==NEW_SHA
    data=stored["runs"]
    refs=load(HERE.parent/"coverage"/"runs.json.gz")["cases"]
    if verify:
        assert len(data)==3*6*len(MODES) and summarize(data)==load(resp)
        for key,z in data.items():
            _,org,repo,cb,mode,lag=key.split("/")
            other=refs[f"new/B/{org}/{repo}"]["logs"]
            assert len(z["reads"])==len(other)
            if mode!="server":
                for r,s in zip(z["reads"],other):
                    assert r[:2]==[s["prefix"],s["anchor"]]
                    observed=s["arms"][cb+"/"+mode]
                    assert r[7:9]==[observed.get("posting_bytes",0),observed.get("body_bytes",0)]
        print("Verified",len(data),"TCP runs.");return
    with TemporaryDirectory(dir=HERE,prefix="wire-db-") as td:
        folder=Path(td)
        plans={}
        for repo,history in load(src).items():
            ops,_=prepare(history,"B")
            cut=sum(o[0]=="w" for o in ops)//2
            path=folder/("base-"+sha256(repo.encode()).hexdigest()[:8]+".sqlite")
            with closing(BlockStore(path,"filelist",True)) as s:
                i=0
                while s.next_id<cut:
                    o=ops[i];i+=1
                    if o[0]=="w":assert s.append(*o[1:])
                assert s.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
            plans[repo]=(path,ops[i:],refs["new/B/"+repo]["logs"])
        rng=Random(SEED)
        for b in range(3):
            for repo in rng.sample(sorted(plans),len(plans)):
                base,tail,rows=plans[repo]
                for cap,mode,lag in rng.sample(MODES,len(MODES)):
                    key=f"{b}/{repo}/{cap}/{mode}/{lag}"
                    if key in data:continue
                    path=folder/"branch.sqlite";copyfile(base,path)
                    data[key]=run(path,tail,rows,cap,mode,lag);path.unlink()
                save(rawp,stored)
                print(b+1,repo,flush=True)
    save(resp,summarize(data))


if __name__=="__main__":
    main()
