"""Score generated rankings only after their distinct locks; compare frozen graph against true alternatives."""
import gzip,json
from collections import defaultdict,Counter
import numpy as np
from data_io import *
from score import metric
def duo(items,new,old):
    n=len(items)
    projects=sorted(set(i[3] for i in items));ids={r:j for j,r in enumerate(projects)};g=np.array([ids[i[3]] for i in items])
    d=np.array([np.array(i[-1][new][:5])-i[-1][old][:5] for i in items])
    ns=np.bincount(g);totals=np.vstack([np.bincount(g,weights=d[:,k],minlength=len(ns)) for k in range(5)]).T
    rng=np.random.default_rng(261118);bs=[]
    for z in range(20):
        ix=rng.integers(len(ns),size=(500,len(ns)));bs.extend((totals[ix].sum(axis=1)/ns[ix].sum(axis=1)[:,None]).tolist())
    rng=np.random.default_rng(181126);T=abs(totals[:,0].sum());n_greater=0
    for z in range(50):
        flips=(2*rng.integers(0,2,(500,len(ns)))-1)*totals[:,0]
        n_greater+=np.sum(abs(flips.sum(axis=1))>=T)
    return {"delta":d.mean(axis=0).tolist(),"ci":np.quantile(bs,[.025,.975],axis=0).tolist(),
       "macro":(totals/ns[:,None]).mean(axis=0).tolist(),"wins":int((d[:,0]>0).sum()),"losses":int((d[:,0]<0).sum()),"p_sign":(1+int(n_greater))/25001}
def describe(items,pairs):
    cols=list(items[0][-1]);n=len(items)
    stats={}
    for a in cols:
        arr=np.array([i[-1][a] for i in items])
        stats[a]={"hits1":int(arr[:,0].sum()),"hits3":int(arr[:,1].sum()),"hits5":int(arr[:,2].sum()),"mrr":arr[:,3].mean(),"packed":int(arr[:,4].sum()),"mean_tokens":arr[:,5].mean()}
    return {"rows":n,"repos":len({i[3] for i in items}),"stats":stats,"contrasts":{new+"-"+old:duo(items,new,old) for new,old in pairs if new in cols and old in cols}}
def goldcols():
    gs=defaultdict(list)
    for p in files("java","test")+files("python","test"):
        gs[panel_name(p.stem)].extend(pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist())
    return gs
def main():
    gs=goldcols()
    base={}
    for which in ["java","python"]:
        for panel,i,k,pr,sz,h,edge,arms in gz(D/(which+".pred.jsonl.gz")):
            if k==3:base[panel,i]=arms
    sha_assoc=read("assoc_prediction_lock.json")["sha256"];assert sha(D/"assoc.pred.jsonl.gz")==sha_assoc
    assoc=defaultdict(list)
    for stage,panel,i,pr,h,sz,arms in gz(D/"assoc.pred.jsonl.gz"):
        if stage=="primary":
            old=base[panel,i]
            assert old["graph"]==arms["graph"]
            arms["owner"]=old["owner"]
        scores={a:metric(s,sz,gs[panel][i]) for a,s in arms.items()}
        assoc[stage+"_"+panel.split("_")[0]].append([panel,i,3,pr,scores])
    pairs=[("learned","graph"),("learned","shuffled"),("graph","owner")]
    out={k:describe(rows,pairs) for k,rows in assoc.items()}
    a=out["primary_java"]["contrasts"]
    p1=a["learned-graph"]["p_sign"];p2=a["graph-owner"]["p_sign"]
    def holm(p,q):return min(1.,2*p) if p<=q else min(1.,max(p,2*q))
    write("association_results.json",{"sets":out,"holm_java3":{"learned_vs_graph":holm(p1,p2),"graph_vs_owner":holm(p2,p1)}})
    source=list(gz(D/"structure.pred.jsonl.gz"));assert sha(D/"structure.pred.jsonl.gz")==read("structure_decision_lock.json")["sha256"]
    newf={(stage,panel,i):d for stage,panel,i,d in source}
    structure={}
    for stage,file in [("public","java.pred.jsonl.gz"),("new","strict_java.pred.jsonl.gz")]:
        rr=[]
        for panel,i,k,pr,sz,h,n,arms in gz(D/file):
            if k!=3:continue
            scores={a:metric(s,sz,gs[panel][i]) for a,s in {**arms,**newf[stage,panel,i]}.items()}
            rr.append([panel,i,3,pr,scores])
        structure[stage]=describe(rr,[("degree","owner"),("activation","degree"),("graph","degree"),("graph","activation"),("graph","owner"),("graph","publisher_bm25")])
    write("structure_results.json",structure)
    if not (D/"paired_decision_lock.json").exists():return
    lookup={};allret={}
    for d in read("paired_decision_lock.json")["runs"]:
        dest=D/("paired_"+d["config"]+".json")
        assert sha(dest)==d["output_sha"]
        for panel,i,k,num,rank in json.loads(dest.read_bytes()):
            lookup[panel,i,k]=rank;allret[panel,i,k]=num
    assert len(lookup)==640
    per=defaultdict(list);allstrict=defaultdict(list);scores_both={};n_out={}
    for panel,i,k,pr,sz,h,e,arms in gz(D/"strict_java.pred.jsonl.gz"):
        bound=len(sz)
        original={a:metric(s,sz,gs[panel][i]) for a,s in arms.items()}
        allstrict[k].append([panel,i,k,pr,original])
        found=lookup.get((panel,i,k))
        if found is None:continue
        original=dict(original,binary=metric(found,sz,gs[panel][i]))
        per[k].append([panel,i,k,pr,original]);scores_both[panel,i,k]=original
        n_out[panel,i,k]=int(gs[panel][i] in found[:allret[panel,i,k]])
    paired={str(k):describe(q,[("graph","binary"),("owner","binary"),("graph","owner"),("graph","publisher_bm25")]) for k,q in per.items()}
    strata={}
    for k,items in per.items():
        strata[k]={panel:{a:sum(i[-1][a][0] for i in items if i[0]==panel) for a in ("graph","binary","publisher_bm25")} for panel in sorted(set(i[0] for i in items))}
    long_minus_short={}
    for arm in ("binary","graph","publisher_bm25"):
        items=[(i[0],i[1],10,i[3],{"long":i[-1][arm],"short":scores_both[i[0],i[1],3][arm]}) for i in per[10]]
        long_minus_short[arm]=duo(items,"long","short")
    ret={str(k):{"mean_returned":float(np.mean([n for (*_,kk),n in allret.items() if k==kk])),
        "gold_in_returned":sum(n for (*_,kk),n in n_out.items() if k==kk)} for k in (3,10)}
    write("holdout_results.json",{"strict":{k:describe(q,[("graph","owner"),("graph","publisher_bm25")]) for k,q in allstrict.items()},"paired":paired,"strata":strata,"long_minus_short":long_minus_short,"before_filling_original_order":ret})
    with gzip.open(D/"strict.scores.jsonl.gz","wt",encoding="utf8") as out:
        for k,items in allstrict.items():
            for i in items:
                if (i[0],i[1],k) in scores_both:i[-1]=scores_both[i[0],i[1],k]
                out.write(json.dumps(i,separators=(",",":"))+"\n")
if __name__=="__main__":main()
