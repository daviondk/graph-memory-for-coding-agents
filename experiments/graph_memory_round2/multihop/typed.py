"""Cross-fitted term association at a directed reference, estimated only on HotpotQA train."""
from pipeline import ROOT,IN,CACHE,key,h,dump,writegz,loadgz,slim,select
from transfer import fit
from direction import extra
from features import tok,bag,alias,stem,STOP,pair_features
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import gzip,itertools,json,math,time,zlib
import numpy as np
import pyarrow.parquet as pq
from scipy.stats import binomtest

BINS=2**19
def code(s):return zlib.crc32(s.encode("utf8"))
def terms(seq):
    return [stem(w) for w in seq if len(w)>1 and w not in STOP and not w.isdigit()]
def cross(query,words):
    # Names were removed; fixed hash features bound memory for publicly reproducible CPU estimates.
    words=sorted(set(words))[:18]
    return np.unique(np.array([(code(q)*1000003 ^ code(w))%BINS for q in query for w in words],dtype=np.int32))
def scan(item):
    uid,q,titles,docs=item
    nodes,meta,bms,pairs,x,_,edges,_,_=pair_features(item)
    roles,_=extra(item,nodes,bms,pairs,edges)
    graph=np.asarray(x,np.float32)[:,:42]
    role=np.hstack((graph,np.asarray(roles,np.float32)[:,:18]))
    seqs=[[tok(z) for z in p] for p in docs];tseq=[(tok(t),tok(alias(t))) for t in titles]
    query=terms(tok(q))
    info=[]
    for pi,((i,j),(a,b)) in enumerate(zip(pairs,edges)):
        for u,v,found in ((i,j,a),(j,i,b)):
            if not found:continue
            tn=set(terms(tseq[u][0]))|set(terms(tseq[v][0]))
            qs=sorted(set(query)-tn)[:12]
            seq=seqs[u]
            flattened=tuple(itertools.chain.from_iterable(seq))
            dense=[k for k,n in sorted(Counter(terms(flattened)).items(),key=lambda p:(-p[1],p[0])) if k not in tn][:18]
            wind=[];place=[]
            def collect(row,pos,end):
                return ["L:"+w for w in terms(row[max(0,pos-5):pos]) if w not in tn]+["R:"+w for w in terms(row[end:end+5]) if w not in tn]
            for k in found:
                row=seq[k]
                seen=set()
                for label in sorted(set(tseq[v]),key=lambda form:(-len(form),form)):
                    if not label:continue
                    for m,w in enumerate(row):
                        if (w!=label[0] or row[m:m+len(label)]!=label or m in seen):continue
                        seen.add(m);wind.extend(collect(row,m,m+len(label)))
                        if flattened:
                            pos=sum(len(ss) for ss in seq[:k])+m
                            jitter=1+int(key(uid+"|"+titles[u]+"|"+titles[v])[:8],16)%max(1,len(flattened)-1)
                            center=(pos+jitter)%len(flattened)
                            place.extend(collect(flattened,center,center+len(label)))
            info.append((pi,(cross(qs,dense),cross(qs,wind),cross(qs,place))))
    return {"id":uid,"titles":titles,"group":titles[max(range(len(titles)),key=lambda i:(bms[i],key(uid+"|"+titles[i])))].casefold()},role,info
def corpus():
    trgold=json.loads((CACHE/"train_gold.json").read_text(encoding="utf8"))
    tr=[]
    for batch in pq.ParquetFile(IN/"train-half.parquet").iter_batches(batch_size=512,columns=["id","question","context"]):
        tr.extend(slim(r) for r in batch.to_pylist() if r["id"] in trgold)
    old={r["id"] for r in loadgz(ROOT/"transfer_predictions.jsonl.gz") if r["dataset"]=="w2"}
    tab=pq.read_table(IN/"2wiki-dev.parquet",columns=["_id","type","question","context"]).to_pylist()
    rank=sorted((r for r in tab if r["type"]!="bridge_comparison"),key=lambda r:key("external-wiki-261118|"+r["_id"]))
    assert old=={r["_id"] for r in rank[:2000]}
    target=[]
    for r in rank[2000:6000]:
        docs=json.loads(r["context"]); target.append((r["_id"],r["question"],[d[0] for d in docs],[d[1] for d in docs]))
    return sorted(tr,key=lambda r:r[0]),sorted(target,key=lambda r:r[0]),trgold
def counters(items,ys):
    # Separate counts by training question fold for honest out-of-fold learned features.
    allc=np.zeros((3,3,BINS),np.int32); pos=np.zeros_like(allc); ns=np.zeros((3,2),np.int64)
    for (meta,_,edges),y in zip(items,ys):
        fold=int(key(meta["id"]+"|relation")[:8],16)%3
        for pi,features in edges:
            ns[fold,0]+=1;ns[fold,1]+=int(y[pi])
            for view,ids in enumerate(features):
                allc[fold,view,ids]+=1
                if y[pi]:pos[fold,view,ids]+=1
    def stats(folds):
        c=allc[folds].sum(0);p=pos[folds].sum(0);n,s=ns[folds].sum(0);prior=s/n
        return np.log((p+12*prior)/(c-p+12*(1-prior))*(1-prior)/prior).astype(np.float32)
    return [stats([i for i in range(3) if i!=j]) for j in range(3)]+[stats([0,1,2])]
def enrich(items,lookups,train):
    enrich=[]
    for meta,r,edges in items:
        tab=lookups[int(key(meta["id"]+"|relation")[:8],16)%3 if train else 3]
        features=np.full((len(r),3,3),-np.inf,np.float32)
        for pi,values in edges:
            for v,ids in enumerate(values):
                if not len(ids):continue
                score=np.sort(tab[v,ids])
                ft=[score[-1],score[-3:].mean(),score.mean()]
                features[pi,v]=np.maximum(features[pi,v],ft)
        features[~np.isfinite(features)]=0
        enrich.append(np.hstack((r,features.reshape(len(r),9))))
    return np.concatenate(enrich)
def learn():
    start=time.perf_counter();tr,te,train_gold=corpus()
    def extract(data):
        with ProcessPoolExecutor(max_workers=3) as ex:return list(ex.map(scan,data,chunksize=10))
    train=extract(tr);test=extract(te); print("features",len(train),len(test),round(time.perf_counter()-start,2),flush=True)
    ys=[np.array([set(pair)==set(train_gold[r["id"]]) for pair in itertools.combinations(r["titles"],2)],np.int8) for r,x,e in train]
    lookup=counters(train,ys);A=enrich(train,lookup,True);B=enrich(test,lookup,False)
    Y=np.concatenate(ys)
    baseline=list(range(60));whole=list(range(60,63));window=list(range(63,66));shift=list(range(66,69))
    arms={"graph":list(range(42)),"roles":baseline,"roles_whole":baseline+whole,"roles_edge":baseline+window,
          "whole_edge":baseline+whole+window,"whole_shift":baseline+whole+shift}
    scores={}
    for name,cols in arms.items():
        scores[name]=fit(A[:,cols],Y).decision_function(B[:,cols]); print("fit",name,round(time.perf_counter()-start,2),flush=True)
    beam=json.loads((IN/"2wiki-beam.json").read_text(encoding="utf8"))
    out=[];p=0
    for meta,x,e in test:
        pairs=list(itertools.combinations(range(len(meta["titles"])),2));u=meta["id"]
        ties=[key("|".join((u,*sorted([meta["titles"][i],meta["titles"][j]])))) for i,j in pairs]
        pred={k:list(pairs[select(z[p:p+len(x)],range(len(x)),ties)]) for k,z in scores.items()}
        pred["beam"]=sorted(beam[u]); assert len(set(pred["beam"]))==2
        out.append({**meta,"pred":pred});p+=len(x)
    writegz(out,ROOT/"typed_predictions.jsonl.gz")
    dump({"counts":[len(tr),len(te)],"seconds":time.perf_counter()-start,"prediction_sha256":h(ROOT/"typed_predictions.jsonl.gz"),
          "protocol_before":h(ROOT/"TYPED_PROTOCOL.md"),"sources":{p.name:h(p) for p in [ROOT/"typed.py",IN/"dev.parquet",IN/"2wiki-dev.parquet",IN/"train-half.parquet",IN/"2wiki-beam.json"]}},"typed_lock.json")
def grade():
    assert h(ROOT/"typed_predictions.jsonl.gz")==json.loads((ROOT/"typed_lock.json").read_text())["prediction_sha256"]
    rows=loadgz(ROOT/"typed_predictions.jsonl.gz")
    gold={r["_id"]:{t for t,i in json.loads(r["supporting_facts"])} for r in pq.read_table(IN/"2wiki-dev.parquet",columns=["_id","supporting_facts"]).to_pylist()}
    hits=[]
    for r in rows:
        g=gold[r["id"]];assert len(g)==2
        hits.append({"id":r["id"],"group":r["group"],"hits":{a:int({r["titles"][i] for i in sel}==g) for a,sel in r["pred"].items()}})
    writegz(hits,ROOT/"typed_item_scores.jsonl.gz")
    metrics={a:sum(r["hits"][a] for r in hits) for a in hits[0]["hits"]}
    cont={}
    for a,b in [("whole_edge","roles_whole"),("whole_edge","whole_shift"),("roles_edge","roles"),("roles","graph"),("whole_edge","beam")]:
        d=np.array([r["hits"][a]-r["hits"][b] for r in hits]);n=len(d)
        groups,ii=np.unique([r["group"] for r in hits],return_inverse=True);s=np.bincount(ii,weights=d);c=np.bincount(ii)
        rng=np.random.default_rng(261118);arr=[]
        for _ in range(100):
            ix=rng.integers(len(c),size=(100,len(c)));arr.extend(s[ix].sum(1)/c[ix].sum(1))
        w=int((d>0).sum());l=int((d<0).sum())
        cont[a+"-"+b]={"delta":d.mean(),"wins":w,"losses":l,"ci":np.quantile(arr,[.025,.975]).tolist(),"p":binomtest(w,w+l).pvalue if w+l else 1.}
    dump({"n":len(rows),"hits":metrics,"contrasts":cont},"typed_results.json")
    print("results",metrics,cont,flush=True)
if __name__=="__main__":
    import sys
    if sys.argv[1] in ("learn","all"):learn()
    if sys.argv[1] in ("grade","all"):grade()
