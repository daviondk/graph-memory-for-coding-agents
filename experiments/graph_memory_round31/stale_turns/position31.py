"""Label-free position baselines at the exact native budgets already fixed by the primary predictions."""
from collections import Counter
from base31 import D,P,Path,h,sha,read,save,DATA,data
from predict31 import source,QWT,Tokenizer,END,WIDTH
def render(s,mode,cap,tok):
    off=s["off"];n=len(off);text=s["full"];head=s["header"]
    # Prefer the first/last token, search only the opposite edge to meet the exact entire-frame budget.
    for trim in range(0,9):
        opts=[]
        for w in range(max(1,min(n-trim,WIDTH)-12),min(n-trim,WIDTH+8)+1):
            if mode=="first":l=off[trim][0];r=off[trim+w-1][1]
            else:l=off[n-trim-w][0];r=off[n-trim-1][1]
            opts.append((l,r,head+text[l:r]+END,w))
        encs=tok.encode_batch([v[2] for v in opts],add_special_tokens=False)
        matches=[v for v,e in zip(opts,encs) if len(e.ids)==cap]
        if matches:
            l,r,st,w=max(matches,key=lambda v:v[1]-v[0]);break
    else:raise ValueError((s["id"],mode,cap,n))
    return {"source":s["id"],"start":l,"end":r,"native":cap,"utf8_bytes":len(st.encode()),"frame_hash":h(st),
            "text_tokens":len(tok.encode(text[l:r],add_special_tokens=False).ids),"header_tokens":len(tok.encode(head,add_special_tokens=False).ids),
            "turns":[i for i,a,b in [(t[2],t[0],t[1]) for t in s["turns"]] if a<r and b>l],"source_tokens":w,"trim":trim}
def main():
    seal=read(D/"forecast-seal.json");p=read(D/"forecast.json.gz");a=read(D/"access.json.gz");tok=Tokenizer.from_file(str(QWT));out={};counts=Counter()
    for c,qs in data().items():
        hist={s["id"]:s for s in read(DATA/"history"/(c+".json.gz"))["sources"]};rr={};memo={}
        for q in qs:
            for key in set(a[q].values()):
                out[key]={}
                for m in ("first","last"):
                    frames=[]
                    for v in p[key]["turn_pair"]:
                        sid=v["source"];cap=v["native"];mk=(sid,cap,m)
                        if mk not in memo:
                            if sid not in rr:rr[sid]=source(hist[sid],tok)
                            memo[mk]=render(rr[sid],m,cap,tok)
                        z=memo[mk];frames.append(z);counts["n"]+=1;counts["over96"]+=z["source_tokens"]>96;counts["opposite_end_trimmed"]+=z["trim"]>0
                    out[key][m]=frames
    save(D/"position-forecast.json.gz",out);save(D/"position-seal.json",dict(forecast=sha(D/"forecast-seal.json"),additional_protocol=sha(D/"POSITION_CONTROLS_RU.md"),
           output=sha(D/"position-forecast.json.gz"),code=sha(Path(__file__)),counts=counts))
if __name__=="__main__":main()
