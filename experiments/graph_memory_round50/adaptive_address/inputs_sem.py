from paths_a import *
from runtime import enc,dec,model_check
from contexts import SYS,key

def main():
    check();model_check()
    ranks=get(D/"orders.json.gz");assert sha(D/"orders.json.gz")==get(D/"retrieval-seal.json")["orders"]
    source=get(P/"visible.json.gz");lex=get(D/"lex-orders.json.gz");receipts=get(D/"overlap.json.gz")
    prefix=enc("<|im_start|>system\n"+SYS+"<|im_end|>\n<|im_start|>user\nQuestion: ",True)
    one=enc("\nDocument 1:\n");two=enc("\nDocument 2:\n");end=enc("<|im_end|>\n<|im_start|>assistant\n",True)
    prompts={};contexts={};delivered={}
    for q,r in ranks.items():
        question,docs=source[q];catalog={i:(t,b) for i,t,b in docs};first=r["seed"]
        f=enc("\n".join(catalog[first]))[:192];selected={a:r[a] for a in ARMS}
        sec={i:enc("\n".join(catalog[i]))[:192] for i in set(selected.values())}
        historic=set(lex[q]["base4"].values())|set(lex[q]["budget_all5"]);base_limit=min(len(enc("\n".join(catalog[i]))[:192]) for i in historic)
        limit=min(base_limit,min(map(len,sec.values())));pre=prefix+enc(question)[:80]+one+f+two
        records={};baseline={}
        for a,i in selected.items():
            ds=sec[i][:limit];ts=pre+ds+end;k=key(ts);assert prompts.setdefault(k,ts)==ts
            records[a]=[i,k,len(ts)]
            if k not in delivered:delivered[k]=[dec(tuple(f)),dec(tuple(ds))]
        assert len({v[2] for v in records.values()})==1
        cluster=hexb("\0".join(catalog[first]).encode());assert receipts[q]["first"]==cluster
        contexts[q]=dict(seed=first,first=len(f),n=limit,old_n=base_limit,cluster=cluster,refs=records,
            switch=selected["adaptive"]!=selected["dense"])
    put(D/"contexts.json.gz",contexts);put(D/"prompts.json.gz",prompts);put(P/"delivered.json.gz",delivered)
    put(D/"input-seal.json",dict(prompts=sha(D/"prompts.json.gz"),contexts=sha(D/"contexts.json.gz"),delivered=sha(P/"delivered.json.gz"),
            retrieval=sha(D/"retrieval-seal.json"),builder=sha(Path(__file__)),n=len(contexts),unique=len(prompts),logical=len(contexts)*len(ARMS)))
    print("INPUT FROZEN",len(contexts),len(prompts),flush=True)
if __name__=="__main__":main()
