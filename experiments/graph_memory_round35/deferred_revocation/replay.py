from pathlib import Path
import os,sys,hashlib,gzip,json
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[name]="1"
D=Path(__file__).resolve().parent;W=D.parents[1];R34=W/"graph_memory_round34/live_reader";sys.path.insert(0,str(R34))
import live as l
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace
import numpy as np
MODES=("exact","append","periodic4","lazy_read","pending4");CUTS=(25,50,75,100)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,z):
    v=(json.dumps(z,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();p.write_bytes(gzip.compress(v,mtime=0,compresslevel=3) if p.suffix==".gz" else v)
def state():
    return dict(db=set(),waiting=set(),s=Counter())
def clear(a):
    q=a["waiting"]
    if q:
        a["s"]["batches"]+=1;a["s"]["removed"]+=len(q);a["db"].difference_update(q);q.clear()
def update(a,new,lost,how,group,reading):
    db=a["db"];pend=a["waiting"];s=a["s"]
    s["inserts"]+=len(new-db);db.update(new);back=new&pend;s["reactivated"]+=len(back);pend.difference_update(back)
    assert not (lost & pend);s["queued"]+=len(lost);pend.update(lost);s["peak"]=max(s["peak"],len(pend))
    if how=="exact" or (how=="periodic4" and group and group%4==0) or (how=="lazy_read" and reading) or (how=="pending4" and len(pend)>=4):clear(a)
def one(sh):
    liveplan=read(R34/"plan.json");seal=read(R34/"seal.json");prevp=R34/f"forecast-{sh}.json.gz";assert sha(prevp)==seal["forecasts"][prevp.name]
    prev={(r["q"],r["cut"]):r for r in read(prevp)}
    graph,rank,_,patch,_=l.read_models();src=l.ref.TR/f"forecasts-main-{sh}.json.gz"
    assert sha(src)==liveplan["parents"][src.relative_to(W).as_posix()]
    by=defaultdict(list)
    for r in read(src):by[r["t"]].append(r)
    raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl";assert sha(raw)==liveplan["raw"][raw.name]
    index=l.ref.graph_index();traj={};out=[];seen=0
    for byte,obj in l.env.pilot.stream(raw):
        t=obj["session_id"]
        if t not in by:continue
        path,hh=index[t];assert sha(path)==hh;rec=read(path);assert hashlib.sha256(byte).hexdigest()==rec["raw_source"]
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1]);ids,geom=l.geometry(rec)
        first,groups=l.parent.lookup(tr,rec,ids,geom);cuts=l.parent.cuts_for(tr.events);feed=l.FeedIndex()
        seq={a:state() for a in MODES};rr={n["node_id"]:n for n in by[t][0]["rr"]};names=list(ids);pmap={};events=[];slices={};truth=set();ng=0;waiting=0
        def encode(items):
            for edge in sorted(items):
                if edge not in pmap:pmap[edge]=len(pmap)
            return sorted(pmap[e] for e in items)
        for step,e in enumerate(tr.events):
            feed.consume(e);newtruth=set(feed.support);up=newtruth-truth;down=truth-newtruth;truth=newtruth
            b=0
            if e.event_type=="tool_call":waiting+=1
            elif e.event_type=="tool_output":
                waiting-=1;assert waiting>=0
                if waiting==0:ng+=1;b=ng
            readcuts=[c for c,at in zip(CUTS,cuts) if at==step]
            if b or up or down or readcuts:events.append([step,b,readcuts,encode(up),encode(down)])
            for a,entry in seq.items():
                update(entry,up,down,a,b,bool(readcuts));assert entry["db"]==truth|entry["waiting"] and not truth&entry["waiting"]
            assert seq["exact"]["db"]==truth and seq["append"]["db"]==feed.ever
            if not readcuts:continue
            assert seq["lazy_read"]["db"]==truth and not seq["lazy_read"]["waiting"]
            idx=np.flatnonzero(first<=step);_,states=l.parent.truncate(geom,idx,feed,groups);nodes=[names[i] for i in idx];lookup={k:j for j,k in enumerate(nodes)}
            rankn=np.arange(1,len(nodes)+1);sig=l.score(rank,np.column_stack((-np.log(rankn),1/rankn,(len(nodes)-rankn)/max(1,len(nodes)-1))))
            mem={};prior={};hits={}
            for a,entry in seq.items():
                key=frozenset(entry["db"])
                if key not in mem:
                    use=states[a] if a in ("exact","append") else l.parent.truncate(geom,idx,SimpleNamespace(support=entry["db"],ever=feed.ever),groups)[1]["exact"]
                    f,c=l.features(nodes,use,rr);mem[key]=l.score(graph,f),f[:,0],c
                prior[a],role,cost=mem[key];hits[a]=len(entry["waiting"])
            for cut in readcuts:slices[str(cut)]=dict(step=step,group=ng,pending=hits.copy())
            for r in by[t]:
                q=r["q"];allr=r["rr"];avail=np.array([j for j,v in enumerate(allr) if v["node_id"] in lookup]);perm=np.asarray([lookup[allr[j]["node_id"]] for j in avail]);c=cost[perm];rrole=role[perm]
                xx=np.column_stack((np.log1p(rankn),np.log1p(c),rrole,rrole*np.log1p(c)));pc=l.correct(patch,xx);preds={}
                for a in MODES:
                    rankorder=np.argsort(-(sig+prior[a][perm]+pc),kind="stable");preds[a]=[avail[l.prefix(rankorder,c,budget)].tolist() for budget in l.BUDGETS]
                assert preds["exact"]==preds["lazy_read"]
                for cut in readcuts:
                    ref=prev[q,cut];assert preds["exact"]==ref["selected"]["exact"] and preds["append"]==ref["selected"]["append"]
                    out.append([q,t,cut,preds]);seen+=2
        assert waiting==0 and ng>=1 and len(slices)==4
        stats={}
        for a,entry in seq.items():
            s=entry["s"];pending=len(entry["waiting"])
            stats[a]={k:int(s[k]) for k in ("batches","removed","inserts","queued","reactivated","peak")}
            stats[a].update(pending_final=pending,drained_batches=s["batches"]+int(pending>0),drained_removed=s["removed"]+pending)
            assert s["queued"]==s["reactivated"]+s["removed"]+pending
        traj[t]=dict(log=events,groups=ng,states=stats,cuts=slices,pair_count=len(pmap),native_inserts=feed.adds,native_deletes=feed.removes,native_ambiguities=feed.ambiguities)
    assert len(traj)==len(by) and seen==2*len(prev) and len(out)==len(prev)
    pp=D/f"orders-{sh}.json.gz";log=D/f"operations-{sh}.json.gz";put(pp,out);put(log,traj);print("shard",sh,len(traj),len(out),flush=True)
    return pp.name,sha(pp),log.name,sha(log)
def run():
    manifest=read(R34/"manifest.json")
    for name in ("live.py","plan.json","seal.json"):assert sha(R34/name)==manifest.get(name,manifest.get("files",{}).get(name))
    plan=dict(protocol=sha(D/"PROTOCOL_RU.md"),code=sha(Path(__file__)),R34=sha(R34/"manifest.json"),witness=sha(l.WORK/"graph_memory_round21/incremental_binding/stream.py"),R22=sha(l.R22/"forecast.py"),modes=MODES)
    put(D/"source-lock.json",plan)
    with ProcessPoolExecutor(2) as pool:parts=list(pool.map(one,range(8)))
    put(D/"forecast-seal.json",dict(files={k:v for a,b,c,d in parts for k,v in ((a,b),(c,d))},plan=sha(D/"source-lock.json")))
if __name__=="__main__":run()