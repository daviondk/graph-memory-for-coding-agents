"""As-of logical support, union of previously materialized PU edges, and logical-union projection."""
from pathlib import Path
import sys,os,hashlib,json,gzip
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent;W=D.parents[1];R34=W/"graph_memory_round34/live_reader";sys.path.insert(0,str(R34))
import live as l
from types import SimpleNamespace
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import numpy as np
CUTS=(25,50,75,100);MODES=("E","M","L")
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,z):
    v=(json.dumps(z,allow_nan=False,sort_keys=True,separators=(",",":"))+"\n").encode();p.write_bytes(gzip.compress(v,mtime=0,compresslevel=3) if p.suffix==".gz" else v)
def edge_digest(e):
    records=sorted([a,b] for a,b in e);return hashlib.sha256(json.dumps(records,ensure_ascii=True,separators=(",",":")).encode()).hexdigest()
def expand(pairs,groups,done):
    return {(a,b) for i,j in pairs if i in done and j in done for a in groups.get(i,()) for b in groups.get(j,())}
def setup():
    pp=R34/"manifest.json";files=load(pp)["files"]
    for n in ("plan.json","seal.json","outcomes.json.gz","live.py"):assert sha(R34/n)==files[n]
    tests=load(l.ref.TR/"split.json.gz")["test"];tt={r["t"] for r in tests};assert len(tt)==1207 and len(tests)==2000
    subset=sorted(tt,key=lambda t:hashlib.sha256(("R36-materialized-prefix|"+t).encode()).digest())[:12]
    put(D/"plan.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),source=sha(pp),forecast=sha(R34/"seal.json"),audit_ids=subset,raw_source_plan=sha(R34/"plan.json"),model=sha(l.R33/"budget_loss/models.json"),code=sha(Path(__file__))))
def one(sh):
    plan=load(D/"plan.json");targets=set(plan["audit_ids"]);lplan=load(R34/"plan.json");baseline=R34/f"forecast-{sh}.json.gz";assert sha(baseline)==load(R34/"seal.json")["forecasts"][baseline.name]
    hist={(r["q"],r["cut"]):r for r in load(baseline)};src=l.ref.TR/f"forecasts-main-{sh}.json.gz";assert sha(src)==lplan["parents"][src.relative_to(W).as_posix()]
    by=defaultdict(list)
    for row in load(src):by[row["t"]].append(row)
    raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl";assert sha(raw)==lplan["raw"][raw.name];results=[];counts={};aud={};index=l.ref.graph_index()
    graph,rank,_,patch,_=l.read_models()
    for buf,obj in l.env.pilot.stream(raw):
        t=obj["session_id"]
        if t not in by:continue
        fp,hh=index[t];assert sha(fp)==hh;rec=load(fp);assert hashlib.sha256(buf).hexdigest()==rec["raw_source"]
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
        ids,ge=l.geometry(rec);first,groups=l.parent.lookup(tr,rec,ids,ge);nids=list(ids);cuts=l.parent.cuts_for(tr.events);rr={n["node_id"]:n for n in by[t][0]["rr"]}
        output=defaultdict(list);positions={e.call_id:j for j,e in enumerate(tr.events) if e.event_type=="tool_output"}
        for d in rec["g"]["nodes"]:
            nid=d["node_id"]
            if nid in ids and d["kind"]==l.ref.OUTPUT_CHUNK_NODE:
                call=d["attributes"]["call_id"];assert first[ids[nid]]==positions[call];output[call].append(nid)
        assert set(output)==set(groups)
        done=set();material=set();feed=l.FeedIndex();full_by_cut={};ncall=nout=0;old_actual=set();snap=[]
        for step,e in enumerate(tr.events):
            feed.consume(e)
            if e.event_type not in ("tool_call","tool_output"):continue
            if e.event_type=="tool_output":done.add(e.call_id);nout+=1
            else:ncall+=1
            current={p for p in feed.support if p[0] in done and p[1] in done and p[0] in groups and p[1] in groups}
            if e.event_type=="tool_call":assert current==old_actual
            material|=current;old_actual=current
            if t in targets and e.event_type=="tool_output":
                aa=expand(current,output,done);mm=expand(material,output,done);snap.append([step,len(aa),edge_digest(aa),len(mm),edge_digest(mm)])
            if step not in cuts:continue
            idx=np.flatnonzero(first<=step);_,base=l.parent.truncate(ge,idx,feed,groups)
            _,mid=l.parent.truncate(ge,idx,SimpleNamespace(support=material,ever=feed.ever),groups)
            states=dict(E=base["exact"],M=mid["exact"],L=base["append"]);nodes=[nids[k] for k in idx];inv={k:j for j,k in enumerate(nodes)}
            es={p:{(a,b) for a,b,k in l.edges_by_name(inv,g) if k==2} for p,g in states.items()}
            logs={"E":current,"M":material,"L":{p for p in feed.ever if p[0] in done and p[1] in done and p[0] in groups and p[1] in groups}}
            assert es["E"]<=es["M"]<=es["L"] and all(es[p]==expand(logs[p],output,done) for p in MODES)
            record=dict(step=step,pu=len(nodes),exact=len(es["E"]),material=len(es["M"]),logical=len(es["L"]),once_visible=len(es["M"]-es["E"]),never_visible=len(es["L"]-es["M"]),logical_pairs={p:len(v) for p,v in logs.items()})
            role=None;price=None;pri={};memo={}
            for p,g in states.items():
                key=frozenset(es[p])
                if key not in memo:
                    fx,price=l.features(nodes,g,rr);role=fx[:,0];memo[key]=l.score(graph,fx)
                pri[p]=memo[key]
            n=len(nodes);rankn=np.arange(1,n+1);signal=l.score(rank,np.column_stack((-np.log(rankn),1/rankn,(n-rankn)/max(1,n-1))))
            for r in by[t]:
                q=r["q"];allr=r["rr"];avail=np.array([j for j,u in enumerate(allr) if u["node_id"] in inv]);perm=np.array([inv[allr[j]["node_id"]] for j in avail])
                c=price[perm];v=role[perm];pc=l.correct(patch,np.column_stack((np.log1p(rankn),np.log1p(c),v,v*np.log1p(c))));choices={}
                for p in MODES:
                    order=np.argsort(-(signal+pri[p][perm]+pc),kind="stable");choices[p]=[avail[l.prefix(order,c,b)].tolist() for b in l.BUDGETS]
                for cut,time in zip(CUTS,cuts):
                    if time!=step:continue
                    check=hist[q,cut]["selected"];assert choices["E"]==check["exact"] and choices["L"]==check["append"]
                    full_by_cut[str(cut)]=record;results.append([q,t,cut,choices])
        counts[t]=dict(tool_calls=ncall,tool_outputs=nout,states=full_by_cut)
        if t in targets:aud[t]=snap
    assert len(results)==len(hist) and len(by)==len(counts)
    p=D/f"orders-{sh}.json.gz";g=D/f"graphs-{sh}.json.gz";a=D/f"sample-{sh}.json.gz";put(p,results);put(g,counts);put(a,aud);print("shard",sh,len(counts),len(results),flush=True)
    return {f.name:sha(f) for f in (p,g,a)}
def main():
    setup()
    with ProcessPoolExecutor(2) as pool:parts=list(pool.map(one,range(8)))
    put(D/"forecast-seal.json",dict(files={k:v for r in parts for k,v in r.items()},plan=sha(D/"plan.json")))
if __name__=="__main__":main()