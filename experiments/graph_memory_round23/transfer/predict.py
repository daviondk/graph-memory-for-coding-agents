"""Generate predictions from text-only views; no gold or task-specific fitting."""
from common import *
from collections import Counter, defaultdict
import importlib.metadata
import re
import time
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import CountVectorizer

WORDS=re.compile(r"[A-Za-z0-9_]+")
BUDGET=2048
ARMS=("whole","fine","two_fine","two_rrf","two_ratio","ratio")

def words(s):
    return WORDS.findall(s.lower())

class Lexical:
    def __init__(self,strings):
        self.v=CountVectorizer(analyzer=words,lowercase=False,dtype=np.float64)
        mat=self.v.fit_transform(strings).tocsr()
        counts=mat.data
        lengths=np.asarray(mat.sum(axis=1)).ravel()
        n=mat.shape[0]
        df=np.bincount(mat.indices,minlength=mat.shape[1])
        idf=np.log1p((n-df+.5)/(df+.5))
        normal=1.2*(.25+.75*lengths/max(float(lengths.mean()),1))
        mat.data=counts*2.2/(counts+np.repeat(normal,np.diff(mat.indptr)))*idf[mat.indices]
        self.lookup=mat.tocsc()
    def score(self,q):
        ix=[self.v.vocabulary_[w] for w in set(words(q)) if w in self.v.vocabulary_]
        return np.asarray(self.lookup[:,ix].sum(axis=1)).ravel()

def ordinal(scores):
    ix=np.argsort(-scores,kind="stable")
    ranks=np.empty(len(ix),dtype=np.int64)
    ranks[ix]=np.arange(1,len(ix)+1)
    return ranks

def choose(order,protected,units,parents,cost):
    used=set()
    covered=set()
    keep=[]
    left=BUDGET
    for x in (list(protected)+list(order)):
        i=int(x)
        p=parents[i]
        if i in used or (not units[i]["coarse"] and p in covered):continue
        if cost[i]>left:continue
        used.add(i)
        if units[i]["coarse"]:covered.add(i)
        keep.append(i)
        left-=cost[i]
        if left==0:break
    return keep

def main():
    when=time.monotonic()
    view=get_views()
    vpath=CACHE/"e5.npy"
    receipt=read(ROOT/"encoder-receipt.json")
    assert checksum(vpath)==receipt["vectors"]
    emb=np.load(vpath,allow_pickle=False)
    n=len(view["q"])
    u=view["blocks"];docs=view["documents"];tu=tok()
    assert len(emb)==n+len(u)
    body=[docs[b["doc"]][2][b["a"]:b["b"]] for b in u]
    strings=[docs[b["doc"]][1]+" "+s for b,s in zip(u,body)]
    framed=[render(b,docs) for b in u]
    cost=np.asarray([len(tu.encode(s,add_special_tokens=False).ids) for s in framed])
    raw_cost=np.asarray([len(tu.encode(s,add_special_tokens=False).ids) for s in body])
    words_by_block=[set(words(s)) for s in body]
    c=np.array([i for i,x in enumerate(u) if x["coarse"]],dtype=int)
    f=np.array([i for i,x in enumerate(u) if not x["coarse"]],dtype=int)
    parents=np.asarray([r["parent"] for r in u],dtype=int)
    cidx={p:j for j,p in enumerate(c)}
    parent_idx=np.array([cidx[parents[i]] for i in f])
    lx={k:Lexical([strings[i] for i in ix]) for k,ix in (("c",c),("f",f))}
    groups=defaultdict(list)
    for j,i in enumerate(f):groups[u[i]["doc"]].append(j)
    depth=np.empty((len(f),3))
    for ids in groups.values():
        for k,j in enumerate(ids):
            depth[j]=[k/max(1,len(ids)-1),int(k==0),int(k==len(ids)-1)]
    model=read(WEIGHTS)["models"]["full"]
    mu=np.asarray(model["mean"]);sd=np.asarray(model["scale"]);co=np.asarray(model["coef"])
    assert len(mu)==len(sd)==len(co)==12
    pred=[]
    for j,(qid,tid,q) in enumerate(view["q"]):
        cosine=emb[n:]@emb[j]
        coarse_l=lx["c"].score(q);fine_l=lx["f"].score(q)
        rc=ordinal(1/(60+ordinal(coarse_l))+1/(60+ordinal(cosine[c])))
        lex=ordinal(fine_l)
        rf=ordinal(1/(60+lex)+1/(60+ordinal(cosine[f])))
        corder=c[np.argsort(rc)];forder=f[np.argsort(rf)]
        rparent=rc[parent_idx]
        qt=set(words(q))
        cov=np.array([len(qt&words_by_block[i])/max(1,len(qt)) for i in f])
        features=np.tile(mu,(len(f),1))
        features[:,:9]=np.column_stack([np.log1p(rparent),1/rparent,np.log1p(lex),
               fine_l/max(float(np.max(np.abs(fine_l))),1e-9),cov,np.log1p(raw_cost[f]),depth])
        logit=(features-mu)/sd@co+model["offset"]
        prob=1/(1+np.exp(-np.clip(logit,-200,200)))
        ratio=f[np.argsort(-prob/cost[f],kind="stable")]
        rrf=f[np.argsort(-(1/(60+rparent)+1/(60+lex)),kind="stable")]
        topdocs=list(dict.fromkeys(u[i]["doc"] for i in corder))
        assert len(topdocs)==len(docs)
        arms={}
        for name,ordering,protected in [("whole",corder,[]),("fine",forder,[]),("two_fine",forder,corder[:2]),
                                         ("two_rrf",rrf,corder[:2]),("two_ratio",ratio,corder[:2]),("ratio",ratio,[])]:
            ix=choose(ordering,protected,u,parents,cost)
            text="\n".join(framed[i] for i in ix)
            charged=len(tu.encode(text,add_special_tokens=False).ids)
            assert charged==int(cost[ix].sum())<=BUDGET
            arms[name]={"chosen":ix,"tokens":charged,"text_sha":sha(text.encode())}
        pred.append(dict(q=qid,dialogue=tid,top_documents=topdocs[:5],arms=arms))
        if j%125==0:print("ranked",j,n,round(time.monotonic()-when,1),flush=True)
    rows=save(ROOT/"predictions.json.gz",pred)
    seal=dict(forecasts=rows,input=checksum(ROOT/"input-lock.json"),code=checksum(Path(__file__)),weights=checksum(WEIGHTS),
              encoder=checksum(ROOT/"encoder-receipt.json"),query_count=len(pred),seconds=time.monotonic()-when,
              libraries={name:importlib.metadata.version(name) for name in ("numpy","scipy","scikit-learn","tokenizers")})
    print("forecasts sealed",save(ROOT/"forecast-seal.json",seal),flush=True)
if __name__=="__main__":
    main()
