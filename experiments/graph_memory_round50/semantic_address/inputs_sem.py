from paths_sem import *
from runtime import enc,dec,model_check
from contexts import SYS,key

def main():
    check();model_check()
    ranks=get(D/"orders.json.gz");assert sha(D/"orders.json.gz")==get(D/"retrieval-seal.json")["orders"]
    source=get(OLD/"visible.json.gz");prev=get(REP/"contexts.json.gz")
    prefix=enc("<|im_start|>system\n"+SYS+"<|im_end|>\n<|im_start|>user\nQuestion: ",True)
    one=enc("\nDocument 1:\n");two=enc("\nDocument 2:\n");end=enc("<|im_end|>\n<|im_start|>assistant\n",True)
    prompts={};contexts={};delivered={}
    for q,r in ranks.items():
        question,docs=source[q];catalog={i:(t,b) for i,t,b in docs};first=r["seed"]
        f=enc("\n".join(catalog[first]))[:192];selected={a:r[a] for a in ARMS}
        sec={i:enc("\n".join(catalog[i]))[:192] for i in set(selected.values())}
        limit=min(prev[q]["n"],min(map(len,sec.values())));pre=prefix+enc(question)[:80]+one+f+two
        records={};baseline={}
        for a,i in selected.items():
            ds=sec[i][:limit];ts=pre+ds+end;k=key(ts);assert prompts.setdefault(k,ts)==ts
            records[a]=[i,k,len(ts)]
            if k not in delivered:delivered[k]=[dec(tuple(f)),dec(tuple(ds))]
            if a in ("lex","true"):
                orig=prev[q]["refs"][a];assert i==orig[0] and (k==orig[1])==(limit==prev[q]["n"])
                baseline[a]=orig[1]
        assert len({v[2] for v in records.values()})==1 and len(f)==prev[q]["first"]
        contexts[q]=dict(seed=first,first=len(f),n=limit,old_n=prev[q]["n"],cluster=prev[q]["cluster"],refs=records,
            switch=selected["linked_dense"]!=selected["dense"],old_prompts=baseline)
    put(D/"contexts.json.gz",contexts);put(D/"prompts.json.gz",prompts);put(P/"delivered.json.gz",delivered)
    put(D/"input-seal.json",dict(prompts=sha(D/"prompts.json.gz"),contexts=sha(D/"contexts.json.gz"),delivered=sha(P/"delivered.json.gz"),
            retrieval=sha(D/"retrieval-seal.json"),builder=sha(Path(__file__)),n=len(contexts),unique=len(prompts),logical=len(contexts)*len(ARMS)))
    print("INPUT FROZEN",len(contexts),len(prompts),flush=True)
if __name__=="__main__":main()
