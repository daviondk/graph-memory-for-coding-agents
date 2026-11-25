"""Fit a small dev-only sentence-block reader, then seal its decisions without test labels."""
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import gzip
import json
import math
import os
import sys
for env in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[env]="1"
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19";G=D.parent/"residual_graph"
sys.path.insert(0,str(OLD/"write_learned"))
from features import stream,load,save,sha
DEV=Path("D:/CodexResearch/x20-isetrace-runtime/write-dev-private/projection")
NAMES=["log_parent_rank","recip_parent","log_lex_rank","relative_bm25","query_type_coverage","log_cost","depth","at_front","at_end","output","opposite_role_log_rank","distance_to_best_event"]
FULL=list(range(len(NAMES)));RED=FULL[:-2]
def key(s):return (s["event_id"],s["json_pointer"],s["char_start"],s["char_end"])
def geometry(row,raw,rr):
    ad=row["addresses"];blocks=row["blocks"];ei={tuple(v):i for i,v in enumerate(ad)}
    md={key(s):p["metadata"] for p in raw["pool"] for s in p["source_spans"]}
    parent={};attached=defaultdict(list);meta={}
    for n in rr:
        assert len(n["source_spans"])==1
        sp=key(n["source_spans"][0]);e=ei[sp[:2]];a,b=sp[2:];p=n["node_id"]
        parent[p]=[e,a,b,n["token_count"]];meta[p]=md[sp];attached[e].append((p,a,b))
    owners=[[p for p,l,h in attached[e] if l<=a and b<=h] for e,a,b,c,nbyte in blocks]
    lex=[stream.content_tokens(raw["fields"][ad[e][0]][a:b]) for e,a,b,c,nbyte in blocks]
    bm=stream.BM25Okapi(lex) if any(lex) else None
    nd=Counter(b[0] for b in blocks);seen=Counter();position=[]
    for e,a,b,c,nbyte in blocks:
        j=seen[e];seen[e]+=1
        position.append((j/max(1,nd[e]-1),int(j==0),int(j==nd[e]-1),float(ad[e][1]=="/content")))
    return parent,meta,owners,bm,list(map(set,lex)),position

def features(query,rr,blocks,geom):
    parent,meta,owners,bm,lex,position=geom
    rank=[n["node_id"] for n in rr];assert set(rank)==set(parent)
    places={k:j for j,k in enumerate(rank,1)};worst=len(rr)+1
    rev={"content.tool_argument":"content.tool_output","content.tool_output":"content.tool_argument"}
    linked={}
    for p in reversed(rank):
        m=meta[p]
        if m.get("call_id"):linked[m["call_id"],m["node_kind"]]=places[p]
    words=stream.content_tokens(query);types=set(words)
    scores=np.asarray(bm.get_scores(words)) if bm else np.zeros(len(blocks))
    order=np.argsort(-scores,kind="stable");rlex=np.empty(len(order),int);rlex[order]=np.arange(1,len(order)+1)
    denom=max(float(max(abs(scores),default=0)),1e-9)
    head=parent[rank[0]][0];out=[];rp=[]
    for j,(e,a,b,c,_) in enumerate(blocks):
        owner=min(owners[j],key=places.get) if owners[j] else None
        r=places[owner] if owner else worst;rp.append(r);m=meta.get(owner,{})
        other=linked.get((m.get("call_id"),rev.get(m.get("node_kind"))),worst)
        out.append([math.log1p(r),1/r,math.log1p(rlex[j]),scores[j]/denom,
                    len(types&lex[j])/max(len(types),1),math.log1p(c),*position[j],math.log1p(other),math.log1p(abs(head-e))])
    return np.array(out),np.array(rp),rlex

def choose(rec,blocks,geom,x,rp,rl,model):
    parent,_,owners,_,_,_=geom
    rank=[n["node_id"] for n in rec["rr"]]
    def whole(skip):
        keep=[];left=2048
        for p in rank:
            c=parent[p][3]
            if c<=left:keep.append(p);left-=c
            elif not skip:break
        return keep
    answer={"prefix":whole(False),"skip":whole(True)}
    if "arms" in rec:
        for k in ("prefix","skip"):
            if k in rec["arms"]:assert rec["arms"][k]==answer[k]
    cost=np.array([b[3] for b in blocks])
    def prob(name):
        m=model["models"][name];z=x[:,m["columns"]]
        return 1/(1+np.exp(-np.clip((z-m["mean"])/m["scale"]@m["coef"]+m["offset"],-200,200)))
    full=prob("full");nog=prob("reduced");idx=np.arange(len(cost))
    for arm,val in {"ratio":full/cost,"prob":full,"unprotected":full/cost,"nog":nog/cost,
                    "parent":-rp,"rrf":1/(60+rp)+1/(60+rl)}.items():
        order=np.lexsort((idx,-val));keep=[] if arm=="unprotected" else rank[:2]
        used=defaultdict(list);left=2048
        for p in keep:
            e,a,b,c=parent[p];used[e].append((a,b));left-=c
        assert left>=0
        for j in order:
            e,a,b,c,_=blocks[j]
            if owners[j] and c<=left and all(b<=l or h<=a for l,h in used[e]):
                keep.append("micro/"+str(j));left-=c
                if left==0:break
        answer[arm]=keep
    return answer

def source(stage,i):
    if stage=="dev":return G/"dev500-pu-dense-ranks.json.gz"
    if stage=="rgcn":return G/f"forecasts-rgcn-{i}.json.gz"
    return OLD/"trained_rank"/f"forecasts-main-{i}.json.gz"
def blocks_path(stage,i):
    return OLD/(f"write_transfer/predictions-{i}.jsonl.gz" if stage=="dev" else f"online_write/forecast-{i}.jsonl.gz")
def process(job):
    stage,i=job;training=stage=="dev"
    rows=load(source(stage,i));lookup=defaultdict(list)
    for r in rows:lookup[r["t"]].append(r)
    cache=DEV if training else stream.CACHE
    if training:golds=load(OLD/"write_transfer/gold-spans.json.gz")
    else:model=load(D/"model.json")
    xx=[];labs=[];ids=[];out=[]
    with gzip.open(blocks_path(stage,i),"rb") as sf:
        for line in sf:
            base=json.loads(line);tid=base["t"]
            qs=lookup.pop(tid,[])
            if not qs:
                assert training
                continue
            raw=load(cache/f"{i}-{tid}.json.gz");assert raw["t"]==tid
            ad=base["addresses"];blocks=base["blocks"];text=dict(raw["q"])
            geom=geometry(base,raw,qs[0]["rr"]);used={};picks={}
            for qrec in qs:
                q=qrec["q"];x,rp,rl=features(text[q],qrec["rr"],blocks,geom)
                if training:
                    intervals=defaultdict(list)
                    for sp in golds[q]:
                        eid,ptr,l,h=key(sp);intervals[eid,ptr].append((l,h))
                    target=[any(a<h and l<b for l,h in intervals.get(tuple(ad[e]),())) for e,a,b,c,nbyte in blocks]
                    eligible=[j for j,parents in enumerate(geom[2]) if parents]
                    xx.append(x[eligible]);labs.append(np.array(target)[eligible]);ids.append(q)
                else:
                    arms=choose(qrec,blocks,geom,x,rp,rl,model);picks[q]=arms
                    for nodes in arms.values():
                        for n in nodes:
                            used[n]=blocks[int(n[6:])][:4] if n.startswith("micro/") else geom[0][n]
            if not training:
                out.append({"t":tid,"addresses":ad,"used":used,"picks":picks})
    if training:return np.vstack(xx),np.concatenate(labs),ids
    assert not lookup
    p=D/f"{stage}-decisions-{i}.json.gz";save(p,out);return sha(p)
def fit():
    rankpath=source("dev",0);assert sha(rankpath)==load(G/"dev500-pu-dense-lock.json")["ranks"]
    with ProcessPoolExecutor(2) as pool:chunks=list(pool.map(process,[("dev",i) for i in range(8)]))
    x=np.vstack([s[0] for s in chunks]);y=np.concatenate([s[1] for s in chunks]);ids=[q for _,_,qid in chunks for q in qid]
    assert len(ids)==len(set(ids))==500 and set(ids)=={r["q"] for r in load(rankpath)}
    models={}
    for k,columns in (("full",FULL),("reduced",RED)):
        sc=StandardScaler().fit(x[:,columns]);z=sc.transform(x[:,columns])
        lr=LogisticRegression(C=1,class_weight="balanced",max_iter=2000,random_state=13).fit(z,y)
        models[k]={"columns":columns,"mean":sc.mean_.tolist(),"scale":sc.scale_.tolist(),"coef":lr.coef_[0].tolist(),"offset":float(lr.intercept_[0]),"iters":int(lr.n_iter_[0])}
    save(D/"model.json",{"n":len(y),"positive":int(y.sum()),"questions":len(ids),"names":NAMES,"models":models,"ranks":sha(rankpath),"train_annotations":sha(OLD/"write_transfer/gold-spans.json.gz")})
def predict(stage):
    assert stage in ("dense","rgcn")
    with ProcessPoolExecutor(3) as pool:
        sums=list(pool.map(process,[(stage,i) for i in range(8)]))
    save(D/f"{stage}-forecast-seal.json",{"model":sha(D/"model.json"),"code":sha(D/"reader.py"),"protocol":sha(D/"PROTOCOL_RU.md"),"ranks":{source(stage,i).name:sha(source(stage,i)) for i in range(8)},"files":{f"{stage}-decisions-{i}.json.gz":h for i,h in enumerate(sums)}})
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:predict(sys.argv[1])
