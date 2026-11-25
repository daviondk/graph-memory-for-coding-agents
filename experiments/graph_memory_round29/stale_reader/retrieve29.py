"""Blind retrieval from user-authored turns. No evaluator path and no pooling across document/query state."""
import os,sys,math,re,time
from collections import Counter,defaultdict
os.environ["TOKENIZERS_PARALLELISM"]="false";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="2"
from setup29 import D,P,W,Path,h,sha,read,save
sys.path.append("D:/CodexResearch/x20-r23-multidoc2dial/libs")
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
QWT=Path("D:/CodexResearch/x20-r25-qasper/qwen-tokenizer.json")
E5=Path("D:/CodexResearch/x20-r23-multidoc2dial/model")
def words(s):return Counter(re.findall(r"[^\W_]+",s.casefold()))
def e5_session():
    o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1
    o.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;o.add_session_config_entry("session.intra_op.allow_spinning","0")
    return ort.InferenceSession(str(E5/"model_qint8_avx512_vnni.onnx"),sess_options=o,providers=["CPUExecutionProvider"])
def encode(texts,t,model):
    ids=[t.encode(x,add_special_tokens=False).ids[:510] for x in texts];order=sorted(range(len(ids)),key=lambda i:len(ids[i]))
    out=np.zeros((len(texts),384),dtype=np.float32)
    for j in range(0,len(order),12):
        sel=order[j:j+12];n=max(len(ids[k]) for k in sel)+2;x=np.zeros((len(sel),n),dtype=np.int64);mask=x.copy()
        for l,k in enumerate(sel):
            s=[t.token_to_id("[CLS]"),*ids[k],t.token_to_id("[SEP]")];x[l,:len(s)]=s;mask[l,:len(s)]=1
        v=model.run(None,{"input_ids":x,"attention_mask":mask,"token_type_ids":np.zeros_like(x)})[0]
        emb=(v*mask[:,:,None].astype(np.float32)).sum(axis=1)/mask.sum(axis=1,keepdims=True)
        out[sel]=emb/np.linalg.norm(emb,axis=1,keepdims=True)
    return out
def chunks(src,t):
    out=[]
    for s in src:
        users=[r for r in s["turns"] if r["role"].lower()=="user"];full="";intervals=[]
        for r in users:
            if full:full+="\n"
            st=len(full);full+=r["text"];intervals.append((st,len(full),r["id"]))
        off=t.encode(full,add_special_tokens=False).offsets;n=len(off);last=max(0,n-144)
        for j in sorted(set(min(k,last) for k in range(0,n,96))):
            lo=off[j][0];hi=off[min(n,j+144)-1][1];text=full[lo:hi]
            out.append(dict(source=s["id"],seq=s["sequence"],time=s["time"],start=lo,end=hi,chunk=text,
                 turns=[[tid,max(0,l-lo),min(hi,r)-lo] for l,r,tid in intervals if l<hi and r>lo]))
    return out
def rank_all(question,vec,rows,v,qvec,scope,dates):
    active=[i for i,r in enumerate(rows) if r["seq"]<=scope];n=len(active);docs=[vec[i] for i in active]
    avg=sum(sum(d.values()) for d in docs)/n or 1.
    terms=sorted(words(question));df={w:sum(w in d for d in docs) for w in terms}
    idf={w:math.log1p((n-f+.5)/(f+.5)) for w,f in df.items() if f}
    bm={i:sum(weight*2.2*d[w]/(d[w]+1.2*(.25+.75*sum(d.values())/avg)) for w,weight in idf.items() if w in d) for i,d in zip(active,docs)}
    bl=sorted(active,key=lambda i:(-bm[i],i));dl=sorted(active,key=lambda i:(-float(qvec@v[i]),i))
    ranks={i:1/(60+r) for r,i in enumerate(bl,1)}
    for r,i in enumerate(dl,1):ranks[i]+=1/(60+r)
    def sources(order):
        seen=set();out=[]
        for i in order:
            e=rows[i]["source"]
            if e not in seen:out.append(i);seen.add(e)
        return out
    base=sources(sorted(active,key=lambda i:(-ranks[i],i)))
    return base,sources(bl)
def choose(spec,rows,bows,vec,qvec):
    top,bm=rank_all(spec["query"],bows,rows,vec,qvec,spec["available_until"],None)
    if spec["asof"] is not None and spec["asof"]!=spec["available_until"]:
        gated,_=rank_all(spec["query"],bows,rows,vec,qvec,spec["asof"],None)
    else:gated=top
    a=gated[0];cand=gated[1:8]
    ages=sorted(cand,key=lambda i:(-rows[i]["seq"],i));sec={i:2/(5+k)+1/(5+ages.index(i)+1) for k,i in enumerate(cand,1)}
    temp=max(cand,key=lambda i:(sec[i],-i))
    later=[i for i in cand if rows[i]["seq"]>rows[a]["seq"]];links=sorted(cand,key=lambda i:(-float(vec[a]@vec[i]),i))
    graph=max(later or cand,key=lambda i:(sec[i]+1/(5+links.index(i)+1),-i))
    return {"H":top[:2],"B":bm[:2],"T":[a,temp],"G":[a,graph]}
def make_slots(selected,rows,tok):
    selected={k:sorted(ix,key=lambda i:rows[i]["seq"]) for k,ix in selected.items() if k!="B"}
    out={k:[] for k in selected}
    for j in range(2):
        tables={}
        for arm,ix in selected.items():
            row=rows[ix[j]];text=row["chunk"];head="["+row["time"]+"] ";full=head+text;off=tok.encode(full,add_special_tokens=False)
            profiles={}
            for end in sorted({b for a,b in off.offsets if b>len(head)}|{len(full)}):
                s=full[:end]
                n=len(tok.encode(s,add_special_tokens=False).ids)
                if n>0:profiles[n]=end
            tables[arm]=(profiles,head)
        common=set.intersection(*(set(v[0]) for v in tables.values()));assert common
        n=max(common)
        for arm,ix in selected.items():
            row=rows[ix[j]];profile,head=tables[arm];end=profile[n]-len(head);clip=row["chunk"][:end]
            out[arm].append(dict(source=row["source"],seq=row["seq"],time=row["time"],origin=row["start"],end=row["start"]+end,
                           ids=[tid for tid,l,r in row["turns"] if l<end and r>0],text=head+clip,n=n))
    return out
def main():
    seal=read(D/"input-seal.json");hp=P/"reader-histories.json.gz";tp=P/"reader-questions.json"
    assert sha(hp)==seal["histories"] and sha(tp)==seal["questions"]
    lock=read(W/"graph_memory_round23/transfer/input-lock.json")
    assert all(sha(E5/k)==v for k,v in lock["model_files"].items())
    qw=Tokenizer.from_file(str(QWT));et=Tokenizer.from_file(str(E5/"tokenizer.json"));engine=e5_session()
    hs=read(hp);specs=read(tp);private={};pub={};started=time.monotonic();total_chunks=0
    for case,hist in hs.items():
        qids=[q for q,r in specs.items() if r["case"]==case];quer=sorted({specs[q]["query"] for q in qids})
        rows=chunks(hist,qw);total_chunks+=len(rows)
        em=encode(["query: "+s for s in quer]+["passage: "+r["chunk"] for r in rows],et,engine);qv={s:em[i] for i,s in enumerate(quer)}
        vv=em[len(quer):];bows=[words(r["chunk"]) for r in rows]
        for q in qids:
            s=specs[q];picks=choose(s,rows,bows,vv,qv[s["query"]]);slots=make_slots(picks,rows,qw)
            private[q]=slots
            pub[q]={k:[{key:v for key,v in z.items() if key!="text"} for z in ls] for k,ls in slots.items()}
            pub[q]["B"]=[{"source":rows[i]["source"],"seq":rows[i]["seq"],"time":rows[i]["time"],"origin":rows[i]["start"],"end":rows[i]["end"]} for i in picks["B"]]
        print(case,len(rows),round(time.monotonic()-started,1),flush=True)
    save(P/"retrieval-strings.json.gz",private);save(D/"retrieval.json.gz",pub)
    save(D/"retrieval-seal.json",dict(inputs=sha(D/"input-seal.json"),code=sha(Path(__file__)),private=sha(P/"retrieval-strings.json.gz"),
        public=sha(D/"retrieval.json.gz"),e5=lock["model_files"],qwen_tokenizer=sha(QWT),chunks=total_chunks,questions=len(private)))
if __name__=="__main__":main()
