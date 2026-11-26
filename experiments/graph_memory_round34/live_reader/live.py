"""Replay a trained graph reader on observed prefixes; seal projected selections before scoring."""
import os,sys
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[name]="1"
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from scipy.stats import rankdata
HERE=Path(__file__).resolve().parent;WORK=HERE.parents[1]
R22=WORK/"graph_memory_round22/prefix_read";R33=WORK/"graph_memory_round33"
sys.path.insert(0,str(R22))
import forecast as parent
from forecast import np,ref,env,FeedIndex,geometry,edges_by_name
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
read,save,sha=ref.read,parent.save,ref.sha
BUDGETS=(512,1024,2048)
def read_models():
    graph=read(R33/"relative_structure/weights.json")["models"]["global_role"]
    base=WORK/"graph_memory_round20/factor_reader"
    rank=read(base/"hash64-weights.json")["rank"];meta=read(base/"prior.json")["models"]["shape"]
    patch=read(R33/"budget_loss/models.json")["models"]["cost_worst_0.03"]
    mpatch=read(R33/"graph_ablation/models.json")["metadata.cost_worst_0.03"]
    return graph,rank,meta,patch,mpatch
def score(m,x):return x@np.asarray(m["coef"])+m["intercept"]
def correct(m,x):return (x-m["center"])/m["scale"]@m["weights"]
def prefix(order,cost,budget):
    end=np.searchsorted(np.cumsum(cost[order]),budget,side="right")
    return order[:end].tolist()
def features(nodes,geom,rr):
    n=len(nodes);inv={k:j for j,k in enumerate(nodes)}
    degree=np.zeros((n,8));pairs=edges_by_name(inv,geom)
    for a,b,k in pairs:degree[inv[a],2*k]+=1;degree[inv[b],2*k+1]+=1
    events=Counter(rr[k]["source_spans"][0]["event_id"] for k in nodes);price=[];rows=[]
    for k in nodes:
        u=rr[k];pos=int(k.rsplit(":chunk:",1)[1]);sz=events[u["source_spans"][0]["event_id"]];c=u["token_count"]
        assert 0<=pos<sz
        rows.append([int(k.startswith("output-content:")),np.log1p(c),np.log1p(pos),pos/max(1,sz-1),int(pos==0),int(pos==sz-1),np.log1p(sz)]);price.append(c)
    x=np.array(rows);deg=np.log1p(degree);cent=np.empty_like(deg)
    for role in (0,1):
        at=np.flatnonzero(x[:,0]==role)
        if len(at):cent[at]=(rankdata(deg[at],axis=0,method="average")-.5)/len(at)-.5
    return np.column_stack([x,deg,cent]),np.array(price)
def run_shard(sh):
    graph,rank,meta,patch,mpatch=read_models();p=R22/f"forecast-{sh}.json.gz"
    assert sha(p)==read(R22/"forecast-lock.json")["files"][p.name]
    prior={(r["q"],r["cut"]):r for r in read(p)}
    src=ref.TR/f"forecasts-main-{sh}.json.gz";orig=read(src);by=defaultdict(list)
    for row in orig:by[row["t"]].append(row)
    raw=env.RAW/f"trajectories-{sh:05d}.jsonl";index=ref.graph_index()
    assert sha(raw)==read(HERE/"plan.json")["raw"][raw.name]
    current=read(R33/"budget_loss/test-ranks.json.gz");noedge=read(R33/"graph_ablation/test-ranks.json.gz")
    out=[];term=0
    for binary,obj in env.pilot.stream(raw):
        t=obj["session_id"]
        if t not in by:continue
        path,h=index[t];assert sha(path)==h;rec=read(path)
        assert __import__("hashlib").sha256(binary).hexdigest()==rec["raw_source"]
        tr=parent.adapt_isetrace_record(parent.parse_isetrace_record(obj),source_revision=env.pilot.RAW[1]);ids,g=geometry(rec)
        first,groups=parent.lookup(tr,rec,ids,g);cuts=parent.cuts_for(tr.events);feed=FeedIndex()
        nlist=list(ids);rr={r["node_id"]:r for r in by[t][0]["rr"]}
        for step,e in enumerate(tr.events):
            feed.consume(e)
            if step not in cuts:continue
            idx=np.flatnonzero(first<=step);local,geoms=parent.truncate(g,idx,feed,groups)
            nodes=[nlist[j] for j in idx];lookup={k:j for j,k in enumerate(nodes)}
            priors={};cost=None
            for k,geom in geoms.items():
                feats,cost=features(nodes,geom,rr);priors[k]=score(graph,feats)
            shap=score(meta,feats[:,:7]);size=len(nodes)
            r=np.arange(1,size+1)
            sig=score(rank,np.column_stack([-np.log(r),1/r,(size-r)/max(1,size-1)]))
            for row in by[t]:
                q=row["q"];all_rr=row["rr"];avail=np.array([j for j,u in enumerate(all_rr) if u["node_id"] in lookup])
                perm=np.array([lookup[all_rr[j]["node_id"]] for j in avail])
                c=cost[perm];role=feats[perm,0];x=np.column_stack([np.log1p(r),np.log1p(c),role,role*np.log1p(c)])
                pc=correct(patch,x);s={k:sig+v[perm]+pc for k,v in priors.items()}
                s["frozen"]=sig+priors["exact"][perm];s["metadata"]=sig+shap[perm]+correct(mpatch,x)
                by_method={a:np.argsort(-scores,kind="stable") for a,scores in s.items()}
                by_method["dense"]=np.arange(len(avail))
                if step==cuts[-1]:
                    assert len(avail)==len(all_rr)
                    assert by_method["exact"].tolist()==current[q]["cost_worst_0.03"] and by_method["frozen"].tolist()==current[q]["frozen"]
                    assert by_method["metadata"].tolist()==noedge[q]["metadata.cost_worst_0.03"] and np.array_equal(by_method["exact"],by_method["final"])
                    term+=1
                picked={a:[avail[prefix(order,c,b)].tolist() for b in BUDGETS] for a,order in by_method.items()}
                for cut,epoch in zip((25,50,75,100),cuts):
                    if epoch!=step:continue
                    other=prior[q,cut]
                    assert other["available"]==avail.tolist() and picked["dense"][2]==other["selected"]["dense"]
                    out.append({"q":q,"t":t,"cut":cut,"pilot":other["pilot"],"selected":picked})
    assert term==len(orig) and len(out)==4*len(orig)
    p=HERE/f"forecast-{sh}.json.gz";save(p,out);return p.name,sha(p)
def setup():
    locks=read(env.R18/"isetrace_official/source-lock.json")
    parents=[R33/"relative_structure/weights.json",R33/"budget_loss/models.json",R33/"budget_loss/test-ranks.json.gz",R33/"graph_ablation/models.json",R33/"graph_ablation/test-ranks.json.gz",R22/"forecast-lock.json",R22/"forecast.py",WORK/"graph_memory_round20/factor_reader/prior.json",WORK/"graph_memory_round20/factor_reader/hash64-weights.json"]
    parents.extend(ref.TR/f"forecasts-main-{i}.json.gz" for i in range(8))
    save(HERE/"plan.json",{"code":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md"),"parents":{p.relative_to(WORK).as_posix():sha(p) for p in parents},"raw":{r["path"].split("/")[-1]:r["sha256"] for r in locks if r["path"].startswith("trajectories/")}})
if __name__=="__main__":
    setup()
    with ProcessPoolExecutor(2) as ex: hashes=dict(ex.map(run_shard,range(8)))
    save(HERE/"seal.json",{"forecasts":hashes,"plan":sha(HERE/"plan.json")})

