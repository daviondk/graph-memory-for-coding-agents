"""Sparse graph of context tokens -> roles of subsequently used declarations, cross-fit by repository."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):
    os.environ[key]="1"
import gzip,json,math,pickle,re,time
from collections import Counter,defaultdict
from datetime import datetime,timezone
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from data_io import *
from memory import JP,NO,WORD,pp,wt,encode,features
from experiment import ARMS,read_cache,nt

def tokens(s):
    # Bounded first-occurrence vocabulary, stable after normalization.
    raw=[m.group().lower() for m in WORD.finditer(s) if m.group().lower() not in NO and len(m.group())>1]
    return set(sorted(set(raw)|set(pp(s)))[:64])
def names(text):
    header="\n".join(text.splitlines()[:16])
    hit=JP.search(header)
    if not hit:return []
    name=hit.group(1);return sorted({name.lower(),*pp(name)})
def update(t,q,names_,gold):
    true=names_[gold]
    if not true:return
    # Each task gives unit mass to its actual outcome and to its whole choice set.
    background=Counter()
    for ns in names_:
        for v in ns:background[v]+=1/(len(names_)*len(ns))
    for v,weight in background.items():t[1][v]+=weight
    for v in true:t[0][v]+=1/len(true)
    for u in q:
        for v,weight in background.items():t[3][u,v]+=weight
        for v in true:t[2][u,v]+=1/len(true)
def get(t,q,labs,exclude=None):
    def count(i,k):return t[i].get(k,0)-(exclude[i].get(k,0) if exclude else 0)
    out=[]
    for vs in labs:
        pair=[];prior=[]
        for v in vs:
            pos=count(0,v);bg=count(1,v)
            prior.append((pos+.7)/(bg+.7))
            for u in q:
                a=count(2,(u,v));b=count(3,(u,v))
                if a>1e-5 or b>1e-5:pair.append((math.log((a+.7)/(b+.7)),math.log1p(max(a,0))))
        vals=[p for p,_ in pair];top=sorted(vals,reverse=True)[:3]
        out.append([max(prior,default=1),sum(prior)/max(1,len(prior)),max(vals,default=0),min(vals,default=0),
        sum(top)/3,sum(vals)/max(1,len(vals)),sum(v>0 for v in vals)/max(1,len(q)*len(vs)),max((c for _,c in pair),default=0)])
    return np.array(out,dtype=np.float32)

def validation_roster():
    old=read("roster.json");used=set();meta={}
    for p in files("java","test"):
        repos=pq.read_table(p,columns=["repo_name"]).column(0).to_pylist();meta[p]=repos
        used.update(repos[j] for j,g in old[p.stem])
    result={};audit={}
    for key in sorted({panel_name(p.stem) for p in meta}):
        pool=[];off=0
        for p,repos in meta.items():
            if panel_name(p.stem)!=key:continue
            existing=dict(old[p.stem])
            pool.extend((r in used,hashstr(f"r4extra|{key}|{off+j}"),p.stem,j,off+j,r) for j,r in enumerate(repos) if j not in existing)
            off+=len(repos)
        sample=sorted(pool)[:250]
        audit[key]={"n":len(sample),"reuse_repo":sum(int(s[0]) for s in sample),"repos":len({x[-1] for x in sample})}
        for _,_,pn,j,i,_ in sample:result.setdefault(pn,[]).append((j,i))
    write("validation_roster.json",result);write("validation_roster_audit.json",audit)
def preload(train):
    old=read("roster.json");out={}
    langfiles=files("java","train") if train else files("java","test")+files("python","test")
    for p in langfiles:
        use=dict(old[p.stem]);entries=[]
        for i,row in enumerate(rows(p,["code","context","repo_name"]+(["gold_snippet_index"] if train else []))):
            if i not in use:continue
            labs=[names(s) for s in row["context"]];q=tokens("\n".join(row["code"].splitlines()[-3:]));g=row.get("gold_snippet_index",None)
            if train and not 0<=g<len(labs):continue
            entries.append((use[i],q,labs,g,row["repo_name"]))
        out[p]=entries
    return out
def run():
    began=time.monotonic();validation_roster()
    write("association_lock.json",{"sha256":{k:sha(D/k) for k in ["ASSOCIATION_PROTOCOL_RU.md","association.py","experiment.py","memory.py","validation_roster.json","roster.json"]},"utc":datetime.now(timezone.utc).isoformat()})
    train=preload(True);groups=[tuple(Counter() for _ in range(4)) for i in range(5)];total=tuple(Counter() for _ in range(4))
    def fold(repo):return int(hashstr(repo)[:8],16)%5
    for path,rec in train.items():
        for i,q,ns,g,repo in rec:update(groups[fold(repo)],q,ns,g)
    for tables in groups:
        for a,b in zip(total,tables):a.update(b)
    X=[];Y=[];W=[];width=43
    for p,entries in train.items():
        data,meta=read_cache(p)
        for j,((i,q,ns,g,repo),r) in enumerate(zip(entries,meta,strict=True)):
            assert i==r[0] and g==r[-1] and repo==r[1];lo,hi=data["offset"][j:j+2]
            features_here=data["f3"][lo:hi,:width];assoc=get(total,q,ns,groups[fold(repo)])
            X.append(np.column_stack([features_here,assoc,np.roll(assoc,1+int(r[4][:6],16)%max(1,len(ns)-1),axis=0)]))
            Y.extend([ii==g for ii in range(len(ns))]);W.extend([1 if ii==g else 1/max(1,len(ns)-1) for ii in range(len(ns))])
    X=np.row_stack(X);clfs={}
    for key,cols in [("graph",list(range(43))),("learned",list(range(51))),("shuffled",[*range(43),*range(51,59)])]:
        clf=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,min_samples_leaf=28,learning_rate=.10,l2_regularization=1,random_state=261119,early_stopping=False)
        clfs[key]=(cols,clf.fit(X[:,cols],Y,sample_weight=W))
    with (D/"assoc_models.pkl").open("wb") as f:pickle.dump(clfs,f)
    with gzip.open(D/"association_writes.jsonl.gz","wt",encoding="utf8") as f:
        for p,entries in train.items():
            for i,q,ns,g,repo in entries:f.write(json.dumps([p.stem,i,repo,sorted(q),ns,g],separators=(",",":"))+"\n")
    bytes_store=0
    with gzip.open(D/"association_graph.jsonl.gz","wt",encoding="utf8") as f:
        for j,table in enumerate(total):
            for k,n in sorted(table.items()):f.write(json.dumps([j,k,n],separators=(",",":"))+"\n")
    # Collect, then score each arm in batches instead of reinitializing sklearn on each query.
    results=[];xall=[];offs=[0]
    def remember(panel,i,stage,repo,q,ns,raw,hs,sz):
        m=get(total,q,ns);all_=np.column_stack([raw[:,:43],m,np.roll(m,1+int(hs[:6],16)%max(1,len(ns)-1),axis=0)])
        xall.append(all_);offs.append(offs[-1]+len(ns));results.append((stage,panel,i,repo,hs,sz))
    for p,entries in preload(False).items():
        data,meta=read_cache(p)
        for j,((i,q,ns,g,repo),r) in enumerate(zip(entries,meta,strict=True)):
            assert i==r[0] and repo==r[1];lo,hi=data["offset"][j:j+2];remember(panel_name(p.stem),i,"primary",repo,q,ns,data["f3"][lo:hi],r[4],r[3])
    extra=read("validation_roster.json")
    for p in files("java","test"):
        keep=dict(extra.get(p.stem,[]))
        for j,row in enumerate(rows(p,["code","context","repo_name"])):
            if j not in keep:continue
            q=tokens("\n".join(row["code"].splitlines()[-3:]));ctx=row["context"];raw=features(row["code"],encode(ctx),3)
            remember(panel_name(p.stem),keep[j],"novel_java",row["repo_name"],q,[names(s) for s in ctx],raw,hashstr(row["code"]),[nt(s) for s in ctx])
    xx=np.row_stack(xall);pr={key:m.predict_proba(xx[:,cols])[:,1] for key,(cols,m) in clfs.items()}
    dest=D/"assoc.pred.jsonl.gz"
    with gzip.open(dest,"wt",encoding="utf8") as f:
        for row,lo,hi in zip(results,offs,offs[1:]):
            ra={key:np.argsort(-prob[lo:hi],kind="stable").tolist() for key,prob in pr.items()}
            f.write(json.dumps([*row,ra],separators=(",",":"))+"\n")
    write("assoc_prediction_lock.json",{"sha256":sha(dest),"utc":datetime.now(timezone.utc).isoformat(),"elapsed":time.monotonic()-began,
          "counts":[len(t) for t in total],"graph_bytes":(D/"association_graph.jsonl.gz").stat().st_size,"models_sha256":sha(D/"assoc_models.pkl")})
if __name__=="__main__":run()
