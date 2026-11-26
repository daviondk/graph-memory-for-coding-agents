"""Matched directed-edge randomization with one graph per trajectory and salt."""
from pathlib import Path
import sys,hashlib,json,os
for n in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[n]="1"
D=Path(__file__).resolve().parent;P=D.parent/"materialized_append";sys.path.insert(0,str(P))
import materialize as up
from materialize import l,load,put,sha,np,CUTS,defaultdict,SimpleNamespace,ProcessPoolExecutor
from scipy.stats import rankdata
SOURCE="33cfd9168b28c67b8924f00a5b38abb1dba7a133ba282d9449ba624cb74c77b2"
SALTS=tuple(f"s{i:02d}" for i in range(8));PRE="R36-edge-count-v1"
def address(n):return hashlib.sha256(n.encode()).hexdigest()
def saltkey(t,s,a,b):
    return hashlib.sha256(f"{PRE}|{s}|{t}|{a}|{b}".encode("ascii")).digest()
def switches(edges,H,t):
    pairs=[tuple(z) for z in edges];allowed={p:i for i,p in enumerate(pairs)};have=set(H);rows=sorted(H);n=len(rows)
    if n<2:return rows,0
    seed=int.from_bytes(hashlib.sha256((PRE+"|switch|"+t).encode("ascii")).digest()[:8],"big");rng=np.random.default_rng(seed);sw=0
    # Fixed computational limit. A no-swap trace is retained in the denominator.
    for j,k in rng.integers(n,size=(min(1024,8*n),2)):
        if j==k:continue
        ai,bi=pairs[rows[j]];aj,bj=pairs[rows[k]]
        if ai==aj or bi==bj:continue
        p1=allowed.get((ai,bj));p2=allowed.get((aj,bi))
        if p1 is None or p2 is None or p1 in have or p2 in have:continue
        have.remove(rows[j]);have.remove(rows[k]);rows[j]=p1;rows[k]=p2;have.update((p1,p2));sw+=1
    assert set(rows)==have and len(have)==len(H)
    return sorted(have),sw
def matched(t,nodes,E,M,L):
    inv={k:j for j,k in enumerate(nodes)};coded=sorted((inv[a],inv[b]) for a,b in L-E);raw=M-E
    h=[j for j,(i,k) in enumerate(coded) if (nodes[i],nodes[k]) in raw];hset=set(h);assert len(h)==len(raw)
    ordered=sorted(h);target_counts=defaultdict(int)
    for j in h:target_counts[coded[j][1]]+=1
    all_target=defaultdict(list)
    for j,(a,b) in enumerate(coded):all_target[b].append(j)
    pglobal=0<len(h)<len(coded);ptarget=any(0<n<len(all_target[g]) for g,n in target_counts.items())
    names=[address(z) for z in nodes];draws={};digest={};detail={}
    hb,sw=switches(coded,h,t)
    for s in SALTS:
        perm=sorted(range(len(coded)),key=lambda j:(saltkey(t,s,names[coded[j][0]],names[coded[j][1]]),j))
        G=sorted(perm[:len(h)]);seen=defaultdict(int);T=[]
        for j in perm:
            b=coded[j][1]
            if seen[b]<target_counts.get(b,0):seen[b]+=1;T.append(j)
        T.sort();assert len(T)==len(h)==len(G)
        draws["G_"+s]=G;draws["T_"+s]=T
    return coded,h,hb,draws,dict(hashes=names,nodes=len(nodes),extra_edges=coded,H=h,swapped=hb,swaps=sw,global_choice=pglobal,target_choice=ptarget,draws=draws)
def degree_increment(coded,sub,n):
    if not sub:return np.zeros((n,2),int)
    p=np.asarray(coded,dtype=int)[sub]
    return np.column_stack((np.bincount(p[:,0],minlength=n),np.bincount(p[:,1],minlength=n)))
def features(base,deg,role_idx,add):
    x=base.copy();changed=np.log1p(deg+add);x[:,11:13]=changed
    for ii in role_idx:
        if len(ii):x[ii,19:21]=(rankdata(changed[ii],axis=0,method="average")-.5)/len(ii)-.5
    return x
def runpart(sh):
    source=P/f"orders-{sh}.json.gz";graphfile=P/f"graphs-{sh}.json.gz";cert=load(P/"forecast-seal.json")
    assert sha(source)==cert["files"][source.name] and sha(graphfile)==cert["files"][graphfile.name]
    control={q:o for q,t,cut,o in load(source) if cut==50};gstats=load(graphfile)
    source=l.ref.TR/f"forecasts-main-{sh}.json.gz";lplan=load(up.R34/"plan.json");assert sha(source)==lplan["parents"][source.relative_to(up.W).as_posix()]
    by=defaultdict(list)
    for row in load(source):by[row["t"]].append(row)
    index=l.ref.graph_index();model,rank,_,patch,_=l.read_models();raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl";assert sha(raw)==lplan["raw"][raw.name]
    metadata={};out={}
    for buf,obj in l.env.pilot.stream(raw):
        t=obj["session_id"]
        if t not in by:continue
        fp,tag=index[t];assert sha(fp)==tag;rec=load(fp);assert hashlib.sha256(buf).hexdigest()==rec["raw_source"]
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1]);ids,geometry=l.geometry(rec);nids=list(ids);first,groups=l.parent.lookup(tr,rec,ids,geometry)
        cut=l.parent.cuts_for(tr.events)[1];done=set();mat=set();feed=l.FeedIndex()
        for step,e in enumerate(tr.events[:cut+1]):
            feed.consume(e)
            if e.event_type=="tool_output":done.add(e.call_id)
            if e.event_type in ("tool_call","tool_output"):mat.update((a,b) for a,b in feed.support if a in done and b in done and a in groups and b in groups)
        idx=np.flatnonzero(first<=cut);nodes=[nids[i] for i in idx];ii={k:j for j,k in enumerate(nodes)}
        _,old=l.parent.truncate(geometry,idx,feed,groups);_,mj=l.parent.truncate(geometry,idx,SimpleNamespace(support=mat,ever=feed.ever),groups)
        native={"E":old["exact"],"M":mj["exact"],"L":old["append"]}
        arcs={k:{(a,b) for a,b,kind in l.edges_by_name(ii,val) if kind==2} for k,val in native.items()};assert arcs["E"]<=arcs["M"]<=arcs["L"]
        gs=gstats[t]["states"]["50"];assert [len(arcs[k]) for k in ("E","M","L")]==[gs[k] for k in ("exact","material","logical")]
        coded,h,hb,draws,audit=matched(t,nodes,arcs["E"],arcs["M"],arcs["L"]);metadata[t]=audit
        rr={n["node_id"]:n for n in by[t][0]["rr"]};base,price=l.features(nodes,native["E"],rr)
        deg=np.rint(np.expm1(base[:,11:13])).astype(int);role=base[:,0];role_idx=[np.flatnonzero(role==v) for v in (0,1)]
        n=len(nodes);all_indices=list(range(len(coded)));per={"E":[],"M":h,"L":all_indices,"swap":hb,**draws}
        computed={};mdegree=degree_increment(coded,h,n);assert np.array_equal(mdegree,degree_increment(coded,hb,n))
        hashes={}
        for name,sub in per.items():
            add=degree_increment(coded,sub,n)
            if name.startswith("T_"):assert np.array_equal(add[:,1],mdegree[:,1])
            if name.startswith(("G_","T_")):assert add[:,0].sum()==mdegree[:,0].sum()
            fx=features(base,deg,role_idx,add)
            if name in native:
                official,_=l.features(nodes,native[name],rr);assert np.array_equal(fx,official),(t,name)
            computed[name]=l.score(model,fx);hashes[name]=hashlib.sha256(add.astype("<i4").tobytes()).hexdigest()
        metadata[t]["degree_sha"]=hashes;assert np.array_equal(computed["M"],computed["swap"])
        ranks=np.arange(1,n+1);sig=l.score(rank,np.column_stack((-np.log(ranks),1/ranks,(n-ranks)/max(1,n-1))))
        for row in by[t]:
            q=row["q"];pool=row["rr"];avail=np.array([j for j,u in enumerate(pool) if u["node_id"] in ii]);perm=np.array([ii[pool[j]["node_id"]] for j in avail]);c=price[perm];roles=role[perm];x=np.column_stack((np.log1p(ranks),np.log1p(c),roles,roles*np.log1p(c)));fix=l.correct(patch,x)
            om={};hfull={}
            for name,prior in computed.items():
                order=np.argsort(-(sig+prior[perm]+fix),kind="stable");hfull[name]=hashlib.sha256(avail[order].astype("<i4").tobytes()).hexdigest()
                om[name]=avail[l.prefix(order,c,2048)].tolist()
                if name in native:assert [avail[l.prefix(order,c,b)].tolist() for b in l.BUDGETS]==control[q][name]
            assert hfull["M"]==hfull["swap"] and om["M"]==om["swap"];out[q]=dict(t=t,picks=om,full_sha=hfull)
    assert set(out)==set(control) and set(metadata)==set(by);p=D/f"selected-{sh}.json.gz";a=D/f"edges-{sh}.json.gz";put(p,out);put(a,metadata);print("shard",sh,len(by),len(out),flush=True)
    return {z.name:sha(z) for z in (p,a)}
def main():
    assert sha(P/"manifest.json")==SOURCE;put(D/"plan.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),source=SOURCE,salts=SALTS,hash_prefix=PRE,code=sha(Path(__file__))))
    with ProcessPoolExecutor(2) as pool:parts=list(pool.map(runpart,range(8)))
    put(D/"forecast-seal.json",dict(files={k:v for part in parts for k,v in part.items()},plan=sha(D/"plan.json")))
if __name__=="__main__":main()