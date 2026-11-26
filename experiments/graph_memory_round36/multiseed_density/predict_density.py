from pathlib import Path
import os,sys,gzip,json,hashlib
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent;COUNT=D.parent/"edge_count_control";MID=D.parent/"multiseed_midpoint";sys.path.insert(0,str(COUNT));import experiment as ec
# midpoint is a parent source for seed-specific lookup and shared reference forecasts.
sys.path.insert(0,str(MID));import midpoint as mm
from experiment import up,l,np,load,put,sha,defaultdict,ProcessPoolExecutor
SEEDS=(17,29,37,41);SALTS=tuple(ec.SALTS);ARMS=("E","M","L",*[f"{f}_{s}" for f in ("G","T") for s in SALTS])
def make_plan():
    sources={};count_manifest=load(COUNT/"manifest.json")
    cm=count_manifest.get("files",count_manifest);midseal=load(MID/"forecast-seal.json");assert sha(COUNT/"forecast-seal.json")==cm["forecast-seal.json"] and midseal["plan"]==sha(MID/"plan.json")
    for i in range(8):
        for nm in [f"edges-{i}.json.gz",f"selected-{i}.json.gz"]:assert sha(COUNT/nm)==cm[nm]
        p=MID/f"predictions-{i}.json.gz";assert midseal["files"][p.name]==sha(p)
        for seed in SEEDS:
            cal,pk,sp=mm.paths(seed,i);r=load(sp);assert sha(cal)==r["rank_weights"] and sha(pk)==next(v["sha"] for v in r["receipts"] if v["file"]==pk.name)
            sources[f"{seed}/{i}"]=[sha(cal),sha(pk),sha(sp)]
    p={"protocol":sha(D/"PROTOCOL_RU.md"),"count":sha(COUNT/"manifest.json"),"mid_forecast":sha(MID/"forecast-seal.json"),"mid_script":sha(MID/"midpoint.py"),"mid_outcomes_sha":sha(MID/"outcomes.json.gz"),"seedpacks":sources,"code":sha(D/"predict_density.py"),"salts":SALTS,"seeds":SEEDS,"arms":ARMS,"salt_namespace":ec.PRE}
    put(D/"plan.json",p)
def shard(i):
    idx=l.ref.graph_index();st=load(COUNT/f"edges-{i}.json.gz");anchor13=load(COUNT/f"selected-{i}.json.gz");mid={v["q"]:v for v in load(MID/f"predictions-{i}.json.gz")};canonical=l.ref.TR/f"forecasts-main-{i}.json.gz";raw=l.env.RAW/f"trajectories-{i:05d}.jsonl";rawplan=load(up.R34/"plan.json");assert sha(canonical)==rawplan["parents"][canonical.relative_to(up.W).as_posix()] and sha(raw)==rawplan["raw"][raw.name];by=defaultdict(list)
    for r in load(canonical):by[r["t"]].append(r)
    weights,rank,_,patch,_=l.read_models();ranks={13:rank};dense={}
    for seed in SEEDS:
        cal,p,_=mm.paths(seed,i);ranks[seed]=load(cal)["rank"];dense[seed]={r["q"]:r["dense"] for r in load(p)}
    out={};audit={"old13":0,"anchors":0,"histories":0,"draws":0,"delta_hashes":0,"q":0}
    for buf,rr in l.env.pilot.stream(raw):
        t=rr["session_id"]
        if t not in by:continue
        fp,tag=idx[t];rec=load(fp);assert sha(fp)==tag and hashlib.sha256(buf).hexdigest()==rec["raw_source"]
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(rr),source_revision=l.env.pilot.RAW[1]);ids,g=l.geometry(rec);first,groups=l.parent.lookup(tr,rec,ids,g);cut=l.parent.cuts_for(tr.events)[1];fit=l.FeedIndex()
        for e in tr.events[:cut+1]:fit.consume(e)
        ii=np.flatnonzero(first<=cut);_,gg=l.parent.truncate(g,ii,fit,groups);names=list(ids);nodes=[names[j] for j in ii];addr={n:j for j,n in enumerate(nodes)};rec13=st[t];assert [ec.address(n) for n in nodes]==rec13["hashes"]
        edges=rec13["extra_edges"];h=rec13["H"];nodecount=len(nodes);exact=gg["exact"];native=l.edges_by_name(addr,gg["append"]);E={(u,v) for u,v,k in l.edges_by_name(addr,exact) if k==2};L={(u,v) for u,v,k in native if k==2};assert sorted((addr[u],addr[v]) for u,v in L-E)==list(map(tuple,edges))
        H={(nodes[edges[j][0]],nodes[edges[j][1]]) for j in h};_,_,_,draws,_=ec.matched(t,nodes,E,E|H,L);assert draws==rec13["draws"];audit["draws"]+=len(draws)
        meta={z["node_id"]:z for z in by[t][0]["rr"]};base,cost=l.features(nodes,exact,meta);role=base[:,0];deg=np.rint(np.expm1(base[:,11:13])).astype(int);ri=[np.flatnonzero(role==k) for k in (0,1)]
        core={};targetadd=ec.degree_increment(edges,h,nodecount)
        for a,sub in {"E":[],"M":h,"L":list(range(len(edges))),**draws}.items():
            add=ec.degree_increment(edges,sub,nodecount);assert hashlib.sha256(add.astype("<i4").tobytes()).hexdigest()==rec13["degree_sha"][a]
            if a.startswith("T_"):assert np.array_equal(add[:,1],targetadd[:,1])
            audit["delta_hashes"]+=1;core[a]=l.score(weights,ec.features(base,deg,ri,add))
        n=nodecount;rn=np.arange(1,n+1);src=np.column_stack((-np.log(rn),1/rn,(n-rn)/max(n-1,1)));signal={s:l.score(ranks[s],src) for s in ranks}
        for r in by[t]:
            q=r["q"];pool=r["rr"];positions=np.array([addr.get(z["node_id"],-1) for z in pool]); selections=[];memo={};sd={}
            for s in (13,*SEEDS):
                dx=np.arange(len(pool)) if s==13 else np.asarray(dense[s][q]);assert sorted(dx)==list(range(len(pool)))
                avail=dx[positions[dx]>=0];local=positions[avail];c=cost[local];v=role[local];x=np.column_stack((np.log1p(rn),np.log1p(c),v,v*np.log1p(c)));fix=l.correct(patch,x);aa=[]
                for a in ARMS:
                    scores=signal[s]+core[a][local]+fix;order=np.argsort(-scores,kind="stable");selected=tuple(map(int,avail[l.prefix(order,c,2048)]))
                    if s==13:
                        assert selected==tuple(anchor13[q]["picks"][a]);audit["old13"]+=1
                    else:
                        if a in ("E","M","L"):assert selected==tuple(mid[q]["seeds"][str(s)][a]);audit["anchors"]+=1
                        if selected not in memo:memo[selected]=len(selections);selections.append(selected)
                        aa.append(memo[selected])
                if s!=13:sd[str(s)]=aa
            out[q]={"t":t,"choices":selections,"seeds":sd};audit["q"]+=1
        audit["histories"]+=1
    assert set(out)==set(mid)==set(anchor13);p=D/f"forecast-{i}.json.gz";put(p,out);print("shard",i,audit,flush=True);return p.name,sha(p),audit
def main():
    make_plan()
    with ProcessPoolExecutor(2) as pool:records=list(pool.map(shard,range(8)))
    put(D/"forecast-seal.json",{"files":{n:h for n,h,_ in records},"audit":{k:sum(z[k] for _,_,z in records) for k in records[0][2]},"plan":sha(D/"plan.json")})
if __name__=="__main__":main()
