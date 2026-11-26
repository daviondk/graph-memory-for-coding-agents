from pathlib import Path
import gzip,hashlib,json,sys,os
for n in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[n]="1"
import numpy as np
D=Path(__file__).resolve().parent
W=D.parents[1];C=W/"graph_memory_round41/causal_budget";N=C.parent/"prefix_native"
sys.path.insert(0,str(C))
from forecast_packets import firstfit,packet
from analyze import crossed
S=(13,17,29,37,41);B=(512,1024,2048)
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if p.suffix==".gz" else b)
def source(folder,name):
    assert sha(folder/name)==read(folder/"manifest.json")["files"][name]
    return read(folder/name)
def fuse(a,b,k):
    ra=np.empty(len(a),int);rb=ra.copy()
    ra[a]=np.arange(1,len(a)+1);rb[b]=np.arange(1,len(a)+1)
    # For equally valued sums, prefer the left input then the local ID.
    return np.lexsort((np.arange(len(a)),ra,-(1/(k+ra)+1/(k+rb))))
def forecast():
    assert sha(D/"PROTOCOL_RU.md")=="f80f9ba80ba9ff313af513d2f44385055a9ae8abf601116052e9569894f69496"
    raw={r["q"]:r for r in read(Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz"))}
    control={q:arms for q,t,arms in source(N,"forecast-packets.json.gz")}
    names=("graph","native","dense","graph_native_60","graph_native_1","graph_dense_60","dense_native_60","head_graph_native_60")
    seals={};matches=0
    for shard in range(8):
        native={q:o for q,t,cut,o in source(N,f"forecast-{shard}.json.gz") if cut==50}
        states=[s for s in source(C,f"state-{shard}.json.gz") if s[2]==50]
        result={}
        for seed in S:
            m=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"] if seed==13 else read(W/f"graph_memory_round21/five_seed/seed-{seed}/calibration.json")["rank"]
            orders={} if seed==13 else {r["q"]:r["dense"] for r in read(W/f"graph_memory_round21/five_seed/seed-{seed}/picks-{shard}.json.gz")}
            prev={q:o for q,t,cut,pilot,o in source(C,f"pred-{seed}-{shard}.json.gz") if cut==50}
            for q,t,cut,at,vis,g,pilot in states:
                orig=raw[q];v=np.asarray(vis,int);n=len(v);ix={j:i for i,j in enumerate(vis)}
                dense=np.arange(n) if seed==13 else np.array([ix[j] for j in orders[q] if j in ix])
                off=np.empty(n);off[dense]=packet.base.linear(m,packet.base.rankx(n))
                z=np.array(orig["x"])[v].copy();z[dense,0]=np.log1p(np.arange(1,n+1))
                _,graph=packet.feature(z,np.array(g),off)
                nn=np.array([ix[j] for j in native[q][f"{seed}/wo_chunk_adjacency"]]);c=np.asarray(orig["c"],int)[v]
                gn=fuse(graph,nn,60)
                seqs=[graph,nn,dense,gn,fuse(graph,nn,1),fuse(graph,dense,60),fuse(dense,nn,60)]
                out=[]
                for budget in B:
                    length=int(np.cumsum(c[graph]).searchsorted(budget//2,side="right"));head=graph[:length];hset=set(head.tolist())
                    prefix=[*head,*(j for j in gn if j not in hset)]
                    packs=[v[firstfit(order,c,budget)].tolist() for order in [*seqs,prefix]]
                    if budget==2048:
                        assert packs[:3]==[prev[q]["graph_firstfit"],control[q][f"{seed}/wo_chunk_adjacency"][1],prev[q]["dense_firstfit"]]
                        matches+=3
                    out.append(packs)
                result.setdefault(q,{"t":t,"pilot":pilot,"pred":{}})["pred"][str(seed)]=out
        file=D/f"packets-{shard}.json.gz";save(file,result);seals[file.name]=sha(file)
    assert matches==30000
    save(D/"forecast-seal.json",dict(seals=seals,checks=matches,arms=names,program=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md")))
def grade():
    sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
    import data as src
    seal=read(D/"forecast-seal.json")
    gold=read(src.nm.OFF/"gold-spans.json.gz");atoms=read(W/"graph_memory_round34/interval_witness/test-atoms.json.gz")
    checks=0;rows=[]
    for shard,file in enumerate(src.sources("test")):
        pp=D/f"packets-{shard}.json.gz";assert sha(pp)==seal["seals"][pp.name]
        predictions=read(pp)
        baseline={r["q"]:r for r in source(C,f"outcomes-{shard}.json.gz") if r["cut"]==50}
        for r in read(file):
            q=r["q"];p=predictions[q];bc=baseline[q]
            assert r["t"]==p["t"]==bc["t"]
            a=[(hi-lo,set(i)) for _,lo,hi,i in atoms[q]];total=sum(x for x,_ in a)
            truth=tuple(src.nm.pilot.SourceSpan.model_validate(sp) for sp in gold[q])
            nodes=[src.nm.pilot.RankedNodeRecord.model_validate(i) for i in r["rr"]]
            cached={};allscore={}
            for s in S:
                ss=[]
                for budget,methods in zip(B,p["pred"][str(s)]):
                    vals=[]
                    for ids in methods:
                        key=tuple(ids)
                        if key not in cached:
                            selected=tuple(nodes[i] for i in ids);cost=sum(n.token_count for n in selected)
                            assert cost<=budget
                            outcome=src.nm.pilot.span_metrics_under_token_budget(selected,truth,budget)
                            active=set(ids);mass=sum(z for z,g in a if active&g)
                            assert int(outcome.full_support)==int(mass==total) and abs(outcome.coverage-mass/total)<1e-12
                            cached[key]=[int(outcome.full_support),outcome.coverage,cost];checks+=1
                        assert cached[key][2]<=budget
                        vals.append(cached[key])
                    ss.append(vals)
                allscore[str(s)]=ss
            rows.append(dict(q=q,t=r["t"],pilot=p["pilot"],eligible=bc["eligible"],values=allscore))
    assert len(rows)==2000
    save(D/"scores.json.gz",rows);groups={}
    for key,rr in [("eligible",[r for r in rows if not r["pilot"] and r["eligible"]]),("nonpilot",[r for r in rows if not r["pilot"]]),("all",rows)]:
        trajectories,idx=np.unique([r["t"] for r in rr],return_inverse=True)
        a=np.array([[r["values"][str(s)] for s in S] for r in rr])
        effects={}
        for i,j,title in [(3,0,"fusion_vs_graph"),(3,1,"fusion_vs_native"),(7,0,"head_vs_graph"),(4,0,"sharp_vs_graph")]:
            diff=a[:,:,2,i,:]-a[:,:,2,j,:]
            effects[title]=dict(delta=diff.mean(axis=(0,1)).tolist(),ci=crossed(diff,idx,S))
        groups[key]=dict(n=len(rr),trajectories=len(trajectories),means=a.mean(axis=(0,1)).tolist(),tests=effects)
    q=groups["eligible"];assert q["n"]==901
    save(D/"results.json",dict(unique_official_scores=checks,arms=seal["arms"],budgets=B,groups=groups))
    print(q["means"][2]);print(q["tests"])
if __name__=="__main__":
    if sys.argv[1]=="predict":forecast()
    if sys.argv[1]=="grade":grade()

