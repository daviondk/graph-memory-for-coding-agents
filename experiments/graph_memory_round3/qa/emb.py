import re,time
import numpy as np,onnxruntime as ort
from tokenizers import Tokenizer
from prepare import P,sha,read,write
SELF=re.compile(r"\b(I|me|my|mine|myself|we|us|our|ours|ourselves)\b",re.I)
OTHER=re.compile(r"\b(you|your|yours|yourself|yourselves)\b",re.I)
def rewrite(text,person,other):
    text=re.sub(r"\b(I|you|we)['’](m|re|ve|ll|d)\b",lambda m:m[1]+" "+{"m":"am","re":"are","ve":"have","ll":"will","d":"would"}[m[2].lower()],text,flags=re.I)
    return OTHER.sub(lambda m:other+("'s" if m[0].lower() in ("your","yours") else ""),SELF.sub(lambda m:person+("'s" if m[0].lower() in ("my","mine","our","ours") else ""),text))
def fields(c):
    turns=c["turns"];people=sorted({t['speaker'] for t in turns});assert len(people)==2
    raw=[t["speaker"]+": "+t["text"]+(" [Image: "+t["caption"]+"]" if t["caption"] else "") for t in turns]
    selftxt=[];swap=[];wins=[];prev=[];nxt=[]
    for i,t in enumerate(turns):
        s=t['speaker'];o=next(x for x in people if x!=s);cap=" [Image: "+t["caption"]+"]" if t["caption"] else ""
        selftxt.append(rewrite(t["text"],s,o)+cap);swap.append(rewrite(t["text"],o,s)+cap)
        left=i-1 if i>0 and t["session"]==turns[i-1]["session"] else -1
        right=i+1 if i+1<len(turns) and t["session"]==turns[i+1]["session"] else -1
        prev.append(left);nxt.append(right)
        wins.append(" ".join(raw[j] for j in [left,i,right] if j>=0))
    return raw,wins,selftxt,swap,prev,nxt
def session(name):
    loc=P/"models"/name
    opt=ort.SessionOptions();opt.intra_op_num_threads=3;opt.inter_op_num_threads=1
    so=ort.InferenceSession(str(loc/"model_quantized.onnx"),opt,providers=["CPUExecutionProvider"])
    tok=Tokenizer.from_file(str(loc/"tokenizer.json"));tok.enable_truncation(192 if name=="encoder" else 384);tok.enable_padding()
    return so,tok
def batch(session,enc):
    ii={k.name for k in session.get_inputs()};inputs=dict(input_ids=np.asarray([x.ids for x in enc],dtype=np.int64),attention_mask=np.asarray([x.attention_mask for x in enc],dtype=np.int64),token_type_ids=np.asarray([x.type_ids for x in enc],dtype=np.int64))
    return session.run(None,{k:v for k,v in inputs.items() if k in ii}),inputs["attention_mask"]
def main():
    data=read("input.json");texts=set()
    for c in data:
        f=fields(c)
        for a in f[:4]:texts.update(a)
        texts.update(q['text'] for q in c['queries'])
    order=sorted(texts,key=lambda x:(len(x),sha(x)));(P/'cache').mkdir(exist_ok=True)
    so,tok=session("encoder");matrix=np.zeros((len(order),384),dtype=np.float32);start=time.time();tokens=0
    for j in range(0,len(order),32):
        enc=tok.encode_batch(order[j:j+32]);(H,),mask=batch(so,enc);z=(H*mask[:,:,None]).sum(axis=1)/mask.sum(axis=1)[:,None]
        matrix[j:j+len(enc)]=z/np.maximum(1e-7,np.linalg.norm(z,axis=1,keepdims=True));tokens+=int(mask.sum())
    np.save(P/'cache/embeddings.npy',matrix);write("cache/index.json",[sha(t) for t in order])
    write("encoder_receipt.json",dict(provider=so.get_providers(),dtype="INT8/float32 output",n=len(order),tokens=tokens,seconds=time.time()-start,emb_sha=sha((P/'cache/embeddings.npy').read_bytes()),ort=ort.__version__))
if __name__=="__main__":main()