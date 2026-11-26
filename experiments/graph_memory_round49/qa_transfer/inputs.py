from common import *
from runtime import enc,dec,model_check
from contexts import SYS,key

def main():
    check();model_check()
    assert get(D/"retrieval-seal.json")["orders"]==sha(D/"orders.json.gz")
    orders=get(D/"orders.json.gz");view=get(P/"visible.json.gz")
    prev=get(P/"seen-documents.json.gz");seen={k:set(v) for k,v in prev.items()}
    marker=enc("<|im_start|>system\n"+SYS+"<|im_end|>\n<|im_start|>user\nQuestion: ",True)
    sep1=enc("\nDocument 1:\n");sep2=enc("\nDocument 2:\n");end=enc("<|im_end|>\n<|im_start|>assistant\n",True)
    ctx={};prompts={};text={}
    for q,r in orders.items():
        question,docs=view[q];catalog={i:(title,body) for i,title,body in docs}
        first=r["seed"];f=enc("\n".join(catalog[first]))[:192];cluster=hexb("\0".join(catalog[first]).encode())
        catalog_hashes={hexb("\0".join(v).encode()) for v in catalog.values()}
        selected={"true":r["true"],"lex":r["lex"],**{"sham"+s:z["second"] for s,z in r["sham"].items()}}
        all_ids=set(selected.values())|set(r["base4"].values())
        docs2={i:enc("\n".join(catalog[i]))[:192] for i in all_ids}
        limit=min(map(len,docs2.values()));prefix=marker+enc(question)[:80]+sep1+f+sep2
        orig_n=min(len(docs2[i]) for i in r["base4"].values())
        records={}
        for a,i in selected.items():
            ds=docs2[i][:limit];ts=prefix+ds+end;k=key(ts)
            assert prompts.setdefault(k,ts)==ts;records[a]=[i,k,len(ts)]
            if k not in text:text[k]=[dec(tuple(f)),dec(tuple(ds))]
        assert set(records)==set(ARMS) and len({v[2] for v in records.values()})==1
        ctx[q]=dict(cluster=cluster,seed=first,refs=records,first=len(f),n=limit,original_n=orig_n,
            switch=r["true"]!=r["lex"],successful=r["true"]!=r["sham"][str(SEEDS[0])]["second"],
            seen={k:cluster in v for k,v in seen.items()},any_seen={k:bool(catalog_hashes&v) for k,v in seen.items()})
    put(D/"contexts.json.gz",ctx);put(D/"prompts.json.gz",prompts);put(P/"delivered.json.gz",text)
    put(D/"input-seal.json",dict(prompts=sha(D/"prompts.json.gz"),contexts=sha(D/"contexts.json.gz"),delivered=sha(P/"delivered.json.gz"),
                               retrieval=sha(D/"retrieval-seal.json"),addendum=sha(D/"ADDENDUM_RU.md"),builder=sha(Path(__file__)),n=len(ctx),unique=len(prompts),logical=len(ctx)*len(ARMS)))
    print("INPUT FROZEN",len(ctx),len(prompts),flush=True)
if __name__=="__main__":main()
