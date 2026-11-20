"""Train using nine conversations and predict the tenth with hidden evidence and answers."""
import collections, re, os, gzip, math, time
os.environ["OPENBLAS_NUM_THREADS"]="2"
import numpy as np
from emb import fields,SELF,OTHER
from prepare import P,read,write,sha
def tokens(s):
    return re.findall(r"[a-z0-9]+",s.lower())
def lexical(docs,queries):
    nd=len(docs);ds=list(map(tokens,docs));avs=np.mean([len(d) for d in ds]);post=collections.defaultdict(list)
    for i,l in enumerate(ds):
        for t,n in collections.Counter(l).items():post[t].append((i,n))
    mat=np.zeros((len(queries),nd),np.float32)
    for j,q in enumerate(queries):
        for t in set(tokens(q)):
            postings=post[t];idf=math.log1p((nd-len(postings)+.5)/(len(postings)+.5))
            for i,f in postings:mat[j,i]+=idf*f*2.5/(f+1.5*(.25+.75*len(ds[i])/max(avs,1)))
    return mat
def relative(M):
    M=np.asarray(M,dtype=np.float32)
    mu=M.mean(axis=1,keepdims=True);sd=M.std(axis=1,keepdims=True)
    return np.clip((M-mu)/np.maximum(.0001,sd),-4,8)
def ranking(M):return np.argsort(np.argsort(-M,axis=1,kind="stable"),axis=1,kind="stable")
def matrices(c,idx,emb):
    raw,wins,selftxt,swap,L,R=fields(c);turns=c['turns'];qs=[x['text'] for x in c['queries']]
    Q=emb[[idx[sha(q)] for q in qs]]
    def calc(text):
        B=lexical(text,qs);V=Q@emb[[idx[sha(t)] for t in text]].T
        return relative(B),relative(V),1/(8+ranking(B))+1/(8+ranking(V))
    bm,dense,rr=calc(raw);bw,dw,_=calc(wins);ba,da,_=calc(selftxt);bs,ds,_=calc(swap)
    L=np.array(L);R=np.array(R);n=len(raw);vt=np.arange(n)
    people=sorted({t['speaker'] for t in turns})
    isown=np.zeros_like(bm);single=[]
    for i,q in enumerate(qs):
        mentions=[p for p in people if re.search(r"\b"+re.escape(p)+r"\b",q,re.I)]; single.append(len(mentions)==1)
        if len(mentions)==1:isown[i]=[1. if t['speaker']==mentions[0] else -1. for t in turns]
    is_q=np.array(['?' in t["text"] for t in turns]);is_self=np.array([bool(SELF.search(t["text"])) for t in turns]);is_other=np.array([bool(OTHER.search(t["text"])) for t in turns])
    length=np.array([min(2.,math.log1p(len(tokens(t['text'])))/3) for t in turns])
    def rep(v):return np.broadcast_to(v,bm.shape).astype(np.float32)
    rawscore=.5*(bm+dense)
    def at(m,v):
        out=m[:,np.maximum(v,0)].copy();out[:,v<0]=0;return out
    flat=[bm,dense,bw,dw,np.maximum(at(rawscore,L),at(rawscore,R)),bm*dense/4,bw*dw/4,isown,
          isown*rawscore/3,rep(is_q),rep(is_self),rep(is_other),rep(length),rep([bool(t["caption"]) for t in turns])]
    def typed(ba,da,left,right,own):
        ml=at(rawscore,left);mr=at(rawscore,right)
        # Only draw a directed link between different speakers inside one session.
        ll=(left>=0)&np.array([turns[max(v,0)]["speaker"]!=turns[i]["speaker"] for i,v in enumerate(left)])
        rl=(right>=0)&np.array([turns[max(v,0)]["speaker"]!=turns[i]["speaker"] for i,v in enumerate(right)])
        ask=ll&is_q[np.maximum(left,0)]
        echo=rl&is_other[np.maximum(right,0)]
        return [ba,da,ba*da/4,own*da/3,ml*ask,ml*ask*is_self,mr*echo,
                ml*ask*own,mr*echo*own,
                rawscore*(own*rep(is_self)-own*rep(is_other))/3]
    tag=typed(ba,da,L,R,isown)
    flip=np.array([int(sha(c["id"]+"|"+t["id"])[:8],16)%2 for t in turns],dtype=bool)
    rand=typed(np.where(flip,bs,ba),np.where(flip,ds,da),np.where(flip,R,L),np.where(flip,L,R),isown*np.where(flip,-1,1))
    m=np.stack(flat+tag+rand,axis=-1).astype(np.float16)
    return m,dict(bm25=bm,dense=dense,fusion=rr),single
NF=14;NT=10
ARMS={"flat":list(range(NF)),"attribution":list(range(NF+4)),"graph":list(range(NF+NT)),"placebo":list(range(NF))+list(range(NF+NT,NF+2*NT))}
def trainmatrix(c,features,gold):
    turns=c['turns'];idmap={v['id']:i for i,v in enumerate(turns)};xs=[];ys=[];ws=[]
    for j,q in enumerate(c["queries"]):
        y=gold[q["id"]];pos=[idmap[s] for s in sorted(set(y["evidence"])) if s in idmap]
        if y['cat']==5 or not pos or len(pos)!=len(set(y["evidence"])):continue
        score=features[j,:,:2].sum(axis=1);neg=~np.isin(np.arange(len(turns)),pos)
        hard=[v for v in np.argsort(-score,kind="stable") if neg[v]][:16]
        rest=np.flatnonzero(neg & ~np.isin(np.arange(len(turns)),hard))
        rand=np.random.default_rng(int(sha(q["id"]+"sample")[:8],16)).choice(rest,size=min(16,len(rest)),replace=False).tolist();sel=pos+hard+rand
        xs.append(features[j,sel,:]);ys.extend([1]*len(pos)+[0]*(len(hard)+len(rand)));ws.extend([.5/len(pos)]*len(pos)+[.5/(len(hard)+len(rand))]*(len(hard)+len(rand)))
    return np.vstack(xs),np.array(ys),np.array(ws)
def fit(x,y,w):
    X=np.column_stack([np.ones(len(x)),x]).astype(np.float64);w=w/w.sum();b=np.zeros(X.shape[1])
    reg=np.ones(len(b))*.012;reg[0]=1e-6
    for step in range(20):
        p=1/(1+np.exp(-np.clip(X@b,-25,25)));grad=X.T@(w*(p-y))+b*reg;H=(X.T*(w*p*(1-p)))@X+np.diag(reg)
        db=np.linalg.solve(H,grad);b-=db
        if max(abs(db))<1e-7:break
    return b
def main():
    started=time.time();data=read("input.json");gold=read("gold.json");idx={s:i for i,s in enumerate(read('cache/index.json'))};em=np.load(P/'cache/embeddings.npy',mmap_mode='r')
    features={};train={};all_ranks={};single={};weights={}
    for c in data:
        key=c['id'];X,base,solo=matrices(c,idx,em);features[key]=X;train[key]=trainmatrix(c,X,gold);all_ranks[key]=base;single[key]=solo
    for c in data:
        k=c["id"];X=features[k];other=[t for key,t in train.items() if key!=k]
        Z,y,w=map(np.concatenate,zip(*other));weights[k]={}
        for arm,cols in ARMS.items():
            b=fit(Z[:,cols],y,w);weights[k][arm]=b.tolist()
            all_ranks[k][arm]=np.einsum('ijk,k->ij',X[:,:,cols],b[1:].astype(np.float32))+b[0]
    preds={};own={}
    for c in data:
        k=c["id"];T=c["turns"];rank={a:np.argsort(-s,axis=1,kind='stable') for a,s in all_ranks[k].items()}
        for j,q in enumerate(c['queries']):
            own[q['id']]=single[k][j];preds[q['id']]={}
            for a,ranking in rank.items():
                ix=ranking[j];preds[q['id']][a]=[[T[i]['id'] for i in ix[:30]],list(dict.fromkeys(T[i]['session'] for i in ix))[:10]]
    (P/'predictions.json.gz').write_bytes(gzip.compress(__import__('json').dumps(preds,separators=(',',':')).encode(),mtime=0));write("weights.json",weights);write("query_owner.json",own)
    write("prediction_lock.json",dict(run_seconds=time.time()-started,sha256={n:sha((P/n).read_bytes()) for n in ("PROTOCOL_RU.md","prepare.py","emb.py","rank.py","input.json","weights.json","predictions.json.gz","models.json")}))
if __name__=="__main__":main()

