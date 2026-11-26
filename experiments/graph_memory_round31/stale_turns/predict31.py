"""Blind localization at frozen source addresses; predicted windows carry replayable source coordinates."""
import os
os.environ.update(OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="2",TOKENIZERS_PARALLELISM="false",MKL_NUM_THREADS="1")
import bisect,collections,math,re,sys,time
from base31 import D,P,W,R29,Path,read,sha,h,save,data,refs,request_id,DATA
from retrieve29 import Tokenizer,QWT,E5,e5_session,np
METHODS=("win_bm","win_hybrid","turn_bm","turn_e5","turn_hybrid","turn_late","turn_ensemble","turn_pair")
WIDTH=96
END="<|endoftext|>"
def word_counts(x):return collections.Counter(re.findall(r"[^\W_]+",x.casefold()))
def ranks(values):
    order=np.argsort(-np.asarray(values),kind="stable");out=np.empty(len(order),dtype=np.int32);out[order]=np.arange(1,len(order)+1);return out
def bm25(q,docs):
    ls=np.array([sum(d.values()) for d in docs]);avg=max(float(ls.mean()),1);score=np.zeros(len(docs))
    for w in word_counts(q):
        freq=np.asarray([d[w] for d in docs]);df=np.count_nonzero(freq)
        if df:score+=math.log1p((len(docs)-df+.5)/(df+.5))*freq*2.2/(freq+1.2*(.25+.75*ls/avg))
    return score
def embeddings(texts,tokenizer,model,keep):
    seq=tokenizer.encode_batch(texts,add_special_tokens=False);ids=[r.ids[:510] for r in seq]
    order=sorted(range(len(ids)),key=lambda i:len(ids[i]));out=np.zeros((len(seq),384),dtype="f");kept={}
    for j in range(0,len(order),12):
        ix=order[j:j+12];n=max(len(ids[k]) for k in ix)+2;x=np.zeros((len(ix),n),dtype="int64");mask=x.copy()
        for z,k in enumerate(ix):
            a=[tokenizer.token_to_id("[CLS]"),*ids[k],tokenizer.token_to_id("[SEP]")];x[z,:len(a)]=a;mask[z,:len(a)]=1
        raw=model.run(None,{"input_ids":x,"attention_mask":mask,"token_type_ids":np.zeros_like(x)})[0]
        for z,k in enumerate(ix):
            hidden=raw[z,:len(ids[k])+2];m=hidden.mean(axis=0);out[k]=m/max(np.linalg.norm(m),1e-12)
            if keep:
                marker=texts[k].index(":")+1
                use=[i+1 for i,(start,end) in enumerate(seq[k].offsets[:510]) if end>marker and any(c.isalnum() for c in texts[k][start:end])]
                vv=hidden[use or [0]];kept[k]=vv/np.maximum(np.linalg.norm(vv,axis=1,keepdims=True),1e-12)
    return out,kept
def source(s,tok):
    used=[r for r in s["turns"] if r["role"].lower()=="user" and r["text"]];assert used
    text="";turns=[]
    for r in used:
        if text:text+="\n"
        start=len(text);text+=r["text"];turns.append((start,len(text),r["id"],r["text"]))
    off=tok.encode(text,add_special_tokens=False).offsets;near_left=[b for a,b in off];near_right=[a for a,b in off]
    last=max(0,len(off)-WIDTH)
    def middle(l,r):
        a=bisect.bisect_right(near_left,l);b=bisect.bisect_left(near_right,r)
        return min(last,max(0,((a+b)//2)-WIDTH//2))
    grid=sorted({min(k,last) for k in range(0,len(off),48)})
    return dict(id=s["id"],time=s["time"],seq=s["sequence"],full=text,turns=turns,off=off,grid=grid,
                starts=[middle(l,r) for l,r,i,v in turns],header="["+s["time"]+" "+s["id"]+"]\n")
def snippet(s,start,size=WIDTH):
    off=s["off"];return s["full"][off[start][0]:off[min(len(off),start+size)-1][1]]
def profiles(s,start,tok,wide=False):
    off=s["off"];l=off[start][0];top=min(len(off),start+WIDTH);bot=start+1 if wide else max(start+1,top-10)
    ends=sorted({off[k-1][1] for k in range(bot,top+1)})
    strings=[s["header"]+s["full"][l:r]+END for r in ends];res={}
    for right,st,enc in zip(ends,strings,tok.encode_batch(strings,add_special_tokens=False)):
        res[len(enc.ids)]=(right,st)
    return res
def deliver(s,starts,tok):
    def get(wide):
        rr={a:profiles(s,a,tok,wide) for a in set(starts.values())};common=set.intersection(*(set(p) for p in rr.values()))
        return rr,common
    rr,common=get(False)
    if not common:rr,common=get(True)
    assert common;size=max(common);out={}
    for m,start in starts.items():
        l=s["off"][start][0];r,st=rr[start][size];payload=s["full"][l:r]
        out[m]={"source":s["id"],"start":l,"end":r,"native":size,"text_tokens":len(tok.encode(payload,add_special_tokens=False).ids),
                "header_tokens":len(tok.encode(s["header"],add_special_tokens=False).ids),"utf8_bytes":len(st.encode("utf8")),
                "frame_hash":h(st),"turns":[tid for a,b,tid,_ in s["turns"] if b>l and a<r]}
    return out
def run_case(c,qq,hist,priv,tok,et,engine):
    src={s["id"]:source(s,tok) for s in hist};skeys=list(src);all_turns=[];index=[];ptr={}
    for sk in skeys:
        ss=src[sk];beg=len(index);all_turns.extend(t[3] for t in ss["turns"]);index.extend([sk]*len(ss["turns"]));ptr[sk]=np.arange(beg,len(index))
    qids=sorted(qq);qv=[];qtoken=[]
    for q in qids:
        pooled,state=embeddings(["query: "+qq[q]],et,engine,True);qv.append(pooled[0]);qtoken.append(state[0])
    v,token=embeddings(["passage: "+t for t in all_turns],et,engine,True)
    bows=[word_counts(t) for t in all_turns];pairs={};access={}
    for k,q in enumerate(qids):
        gb=bm25(qq[q],bows);gd=v@qv[k];hy=1/(60+ranks(gb))+1/(60+ranks(gd))
        ranking=list(dict.fromkeys(index[i] for i in np.argsort(-hy,kind="stable")))
        actual=ranking[:2];oracle=priv[q];access[q]={tag:request_id(q,x) for tag,x in (("actual",actual),("known",oracle))}
        for addr in (actual,oracle):
            key=request_id(q,addr);pairs[key]=(q,sorted(addr,key=lambda sk:src[sk]["seq"]))
    touched=sorted({sk for _,ss in pairs.values() for sk in ss});wg={};wx=[];wb=[]
    for sk in touched:
        s=src[sk];w=[snippet(s,start) for start in s["grid"]];wg[sk]=np.arange(len(wx),len(wx)+len(w));wx.extend(w);wb.extend(word_counts(t) for t in w)
    # Encode each visible source independently of which other physical or diagnostic addresses were requested.
    we=np.empty((len(wx),384),dtype="f")
    for sk in touched:
        ids=wg[sk];we[ids],_=embeddings(["passage: "+wx[i] for i in ids],et,engine,False)
    out={}
    for key,(q,addresses) in sorted(pairs.items()):
        qi=qids.index(q);query=qq[q];starts={};unit={}
        for sk in addresses:
            s=src[sk];ids=ptr[sk];wiki=wg[sk]
            bb=ranks(bm25(query,[bows[i] for i in ids]));ee=ranks(v[ids]@qv[qi])
            late=np.asarray([float((qtoken[qi]@token[i].T).max(axis=1).mean()) for i in ids]);ll=ranks(late)
            mix=1/(60+bb)+1/(60+ee);ensemble=1/(10+bb)+1/(10+ee)+1/(10+ll)
            wb1=ranks(bm25(query,[wb[i] for i in wiki]));we1=ranks(we[wiki]@qv[qi]);wm=1/(60+wb1)+1/(60+we1)
            unit[sk]=ranks(ensemble)
            starts[sk]={"win_bm":s["grid"][int(wb1.argmin())],"win_hybrid":s["grid"][int(wm.argmax())],
                  **{name:s["starts"][int(i)] for name,i in {"turn_bm":bb.argmin(),"turn_e5":ee.argmin(),"turn_late":ll.argmin(),
                                                            "turn_hybrid":mix.argmax(),"turn_ensemble":ensemble.argmax()}.items()}}
        a,b=addresses;cross=v[ptr[a]]@v[ptr[b]].T
        ab=np.stack([ranks(row) for row in cross]);ba=np.stack([ranks(row) for row in cross.T]).T
        joint=1/(5+unit[a][:,None])+1/(5+unit[b][None,:])+.25*(1/(5+ab)+1/(5+ba))
        ii,jj=np.unravel_index(joint.argmax(),joint.shape)
        starts[a]["turn_pair"]=src[a]["starts"][ii];starts[b]["turn_pair"]=src[b]["starts"][jj]
        # All methods use the same Qwen-token budget in each costed source frame and its concatenation.
        frames=[deliver(src[sk],starts[sk],tok) for sk in addresses]
        out[key]={m:[fr[m] for fr in frames] for m in METHODS}
        for m,items in out[key].items():
            st="".join(src[z["source"]]["header"]+src[z["source"]]["full"][z["start"]:z["end"]]+END for z in items)
            assert len(tok.encode(st,add_special_tokens=False).ids)==sum(z["native"] for z in items)
    return dict(case=c,access=access,out=out,n_sessions=len(src),n_turns=len(all_turns),n_window_candidates=len(wx))
def main():
    seal=read(D/"input-seal.json");lock=refs();privfile=P/"privileged-addresses.json.gz";assert sha(privfile)==seal["privileged_channel"]
    assert all(sha(E5/name)==v for name,v in seal["models"].items()) and sha(QWT)==seal["qwen_tokenizer"]
    qq=data();pr=read(privfile);tok=Tokenizer.from_file(str(QWT));et=Tokenizer.from_file(str(E5/"tokenizer.json"));engine=e5_session()
    config=h(sha(Path(__file__))+sha(D/"input-seal.json"));start=time.monotonic();done={};limit=int(sys.argv[1]) if len(sys.argv)>1 else len(qq)
    for c in sorted(qq,key=lambda k:h("r31-order"+k))[:limit]:
        folder=P/"shards"/config;folder.mkdir(exist_ok=True);f=folder/(c+".json.gz")
        if f.exists():
            old=read(f);assert old["config"]==config
        else:
            df=DATA/"history"/(c+".json.gz");assert sha(df)==lock["history"][c]
            old=run_case(c,qq[c],read(df)["sources"],{q:pr[q] for q in qq[c]},tok,et,engine);old["config"]=config;save(f,old)
        done[c]=sha(f);state=dict(done=len(done),total=len(qq),stage="predict",elapsed_s=round(time.monotonic()-start,1),config=config);save(D/"progress.json",state)
        if len(done)%10==0 or len(done)==limit:print(state,flush=True)
    if limit==len(qq):
        rows={};keys={};total=collections.Counter()
        for c in done:
            z=read(P/"shards"/config/(c+".json.gz"));rows.update(z["out"]);keys.update(z["access"]);total.update({i:z[i] for i in ("n_sessions","n_turns","n_window_candidates")})
        save(D/"forecast.json.gz",rows);save(D/"access.json.gz",keys)
        save(D/"forecast-seal.json",dict(code=sha(Path(__file__)),config=config,input=sha(D/"input-seal.json"),forecast=sha(D/"forecast.json.gz"),
               access=sha(D/"access.json.gz"),shards=done,totals=total))
if __name__=="__main__":main()
