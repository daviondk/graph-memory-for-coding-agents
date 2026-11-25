"""Make a question+document input view and freeze four serialized active contexts. No labels in the predictor."""
import gzip,hashlib,json,os,sys
from pathlib import Path
os.environ["TOKENIZERS_PARALLELISM"]="false"
from tokenizers import Tokenizer
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round25/directional_open"
P=Path("D:/CodexResearch/x20-r26-squad-qa");RAW=Path("D:/CodexResearch/x20-r25-squad/dev-v1.1.json")
MODEL=W/"graph_memory_round3/qa/models/reader";ENCT=MODEL/"tokenizer.json";WEIGHTS=MODEL/"model_quantized.onnx"
WP=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
ARMS=("base","right","both","adaptive")
def h(b):return hashlib.sha256(b.encode() if isinstance(b,str) else b).hexdigest()
def sha(p):return h(p.read_bytes())
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def save(p,v):
    b=(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    t=p.with_name(p.name+".tmp");t.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b);os.replace(t,p)
def wire(text,parts):
    s="";spans=[]
    for l,r,anc in parts:
        if s:s+="\n"
        s+="[0:"+str(anc)+"] ";a=len(s);s+=text[l:r];spans.append([a,len(s),l,r])
    return s,spans
def enc(t,s):return t.encode(s,add_special_tokens=False)
def fit(text,z,cap,tok):
    e,l,r,_,anchor,side,_=z;assert e==0
    head=f"[0:{anchor}] ";nh=len(enc(tok,head).ids);room=cap-nh
    if room<1 or l>=r:return []
    body=text[l:r];o=enc(tok,body).offsets
    if not o:return []
    if len(o)>room:
        if side=="R":r=l+o[room-1][1]
        else:l=l+o[-room][0]
    while l<r and len(enc(tok,head+text[l:r]).ids)>cap:
        if side=="R":r-=1
        else:l+=1
    return [[l,r,anchor]] if l<r else []
def match(text,actions,tok,unc):
    def clip(arm,cap):
        rr=actions[arm]
        caps=[cap//2,cap-cap//2] if len(rr)==2 else [cap]
        parts=[part for z,k in zip(rr,caps) for part in fit(text,z,k,tok)]
        s,_=wire(text,parts)
        return parts,len(enc(tok,s).ids),len(enc(unc,s).ids)
    cap=256
    while True:
        items={k:clip(k,cap) for k in ARMS[1:]};prices=[i[1] for i in items.values()]
        if len(set(prices))==1 and max(i[2] for i in items.values())<=256:return items
        cap=min(prices) if min(prices)<cap else cap-1
        assert cap>=0
def main():
    assert sha(RAW)=="95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9"
    assert sha(WEIGHTS)=="fb134f63a53c22ce070ccaedd3a299b57ed546e71ab391579e418e8d0bd69ee6"
    assert sha(ENCT)=="343989712a36cd8b253efeaf8baf6a08b9d2583f78e395e83832e8ee9f8d8ee1"
    assert sha(R/"squad-choices.json.gz")==read(R/"squad-choice-seal.json")["actions"]
    assert sha(R/"squad-opened.json.gz")==read(R/"squad-open-seal.json")["actions"]
    selected=read(R/"squad-choices.json.gz");opens=read(R/"squad-opened.json.gz")
    qs={};docs={}
    for art in read(RAW)["data"]:
        key=art["title"];docs[key]="\n\n".join(z["context"] for z in art["paragraphs"])
        for par in art["paragraphs"]:
            for qa in par["qas"]:
                q=qa["id"]
                if q in selected:qs[q]=[key,qa["question"]]
    assert set(qs)==set(selected)==set(opens) and len(qs)==576 and len(docs)==48
    save(P/"blind-input.json.gz",{"docs":docs,"qs":qs})
    tok=Tokenizer.from_file(str(ENCT));unc=Tokenizer.from_file(str(WP));view=read(P/"blind-input.json.gz")
    jobs={}
    for q,(title,query) in view["qs"].items():
        src=view["docs"][title];rec=selected[q];assert title==rec["t"]
        base=[[l,r,l] for _,l,r in rec["base"]];items=match(src,opens[q]["arms"],tok,unc)
        items["base"]=([],0,0);out={}
        for k,(extra,cost,unc_cost) in items.items():
            w,_=wire(src,base+extra);bw,_=wire(src,base)
            total=len(enc(tok,w).ids);assert total==len(enc(tok,bw).ids)+cost
            out[k]=dict(extra=extra,native_extra=cost,unc_extra=unc_cost,native_wire=total,wire_sha=h(w))
        assert len(set(out[k]["native_wire"] for k in ARMS[1:]))==1
        jobs[q]={"title":title,"base":base,"arms":out}
    save(D/"contexts.json.gz",jobs)
    save(D/"input-lock.json",dict(code=sha(Path(__file__)),plan=sha(D/"PROTOCOL_RU.md"),source=sha(RAW),
        choice=sha(R/"squad-choice-seal.json"),opened=sha(R/"squad-open-seal.json"),cased_tokenizer=sha(ENCT),uncased_tokenizer=sha(WP),
        model=sha(WEIGHTS),view=sha(P/"blind-input.json.gz"),contexts=sha(D/"contexts.json.gz"),questions=len(jobs),articles=len(docs)))
    print(len(jobs),flush=True)
if __name__=="__main__":main()
