from collections import Counter
import json,sys,time
from paths_href import *
from runtime import enc,dec,generate,model_check
from contexts import SYS,key

def input_stage():
    check();model_check()
    ranks=get(D/"orders.json.gz");assert sha(D/"orders.json.gz")==get(D/"retrieval-seal.json")["orders"]
    prefix=enc("<|im_start|>system\n"+SYS+"<|im_end|>\n<|im_start|>user\nQuestion: ",True)
    one=enc("\nDocument 1:\n");two=enc("\nDocument 2:\n");end=enc("<|im_end|>\n<|im_start|>assistant\n",True)
    prompts={};ctx={};cache={};old_tokens={};old_answers={}
    for split,prior in PRIOR.items():
        v=get(VISIBLE[split]/"visible.json.gz");previous=get(prior/"contexts.json.gz")
        manifest=get(prior/"manifest.json")["files"]
        for name in ("prompts.json.gz","answers.json.gz","answer-seal.json"):assert manifest[name]==sha(prior/name)
        ins=get(prior/"prompts.json.gz");out=get(prior/"answers.json.gz");assert set(ins)==set(out)
        assert get(prior/"answer-seal.json")["model"]==get(W/"graph_memory_round46/reader_transfer/plan.json")["model"]
        for k,ts in ins.items():
            assert old_tokens.setdefault(k,ts)==ts and old_answers.setdefault(k,out[k])==out[k]
            cache.setdefault(k,[]).append(split)
        for q,prev in previous.items():
            r=ranks[q];assert r["split"]==split and r["seed"]==prev["seed"]
            question,docs=v[q];catalog={i:(t,b) for i,t,b in docs};f=enc("\n".join(catalog[r["seed"]]))[:192]
            sec={i:enc("\n".join(catalog[i]))[:192] for i in {r[a] for a in ARMS}}
            n=min(prev["n"],min(map(len,sec.values())));head=prefix+enc(question)[:80]+one+f+two;refs={}
            for a in ARMS:
                i=r[a];ts=head+sec[i][:n]+end;k=key(ts);assert prompts.setdefault(k,ts)==ts
                refs[a]=[i,k,len(ts)]
            assert (refs["true"][1]==prev["refs"]["true"][1])==(n==prev["n"])
            ctx[q]=dict(split=split,seed=r["seed"],first=len(f),n=n,old_n=prev["n"],cluster=prev["cluster"],refs=refs)
    reused={k:cache[k] for k,ts in prompts.items() if k in cache and old_tokens[k]==ts}
    copied={k:old_answers[k] for k in reused}
    put(D/"contexts.json.gz",ctx);put(D/"prompts.json.gz",prompts);put(D/"reuse.json.gz",reused);put(P/"cache.json.gz",copied)
    put(D/"input-seal.json",dict(prompts=sha(D/"prompts.json.gz"),contexts=sha(D/"contexts.json.gz"),reused=sha(D/"reuse.json.gz"),
        cached_answers=sha(P/"cache.json.gz"),tail=end,unique=len(prompts),cached=len(reused),new=len(prompts)-len(reused),logical=3*len(ctx),
        retrieval=sha(D/"retrieval-seal.json"),code=sha(Path(__file__))))
    print("inputs",len(ctx),len(prompts),"reused",len(reused),"new",len(prompts)-len(reused),flush=True)

def answer_stage():
    check();props=model_check();seal=get(D/"input-seal.json")
    assert sha(D/"prompts.json.gz")==seal["prompts"] and sha(P/"cache.json.gz")==seal["cached_answers"]
    inp=get(D/"prompts.json.gz");answers=get(P/"cache.json.gz");reuse=set(answers);new=set(inp)-reuse
    assert len(new)==seal["new"];t=time.perf_counter()
    order=sorted(new,key=lambda k:hexb(("r49-infer|"+k).encode()))
    log=P/"new-answers.jsonl";done={}
    if log.exists():
        done=dict(json.loads(line) for line in log.read_text(encoding="utf8").splitlines())
        assert list(done)==order[:len(done)]
    initialized=len(done);answers.update(done)
    with log.open("a",encoding="utf8") as f:
        for k in order[len(done):]:
            a=generate(inp[k]);answers[k]=a;f.write(json.dumps([k,a],ensure_ascii=False)+"\n");f.flush()
    audit={}
    for group in (reuse,new):
        for k in sorted(group,key=lambda k:hexb(("r50-href-repeat|"+k).encode()))[:32]:audit[k]=generate(inp[k])
    plan=get(W/"graph_memory_round46/reader_transfer/plan.json")
    assert set(answers)==set(inp)
    put(D/"answers.json.gz",answers);put(D/"replay.json",audit)
    put(D/"answer-seal.json",dict(answers=sha(D/"answers.json.gz"),replay=sha(D/"replay.json"),model=plan["model"],server=plan["server"],props=props,
        input=sha(D/"input-seal.json"),log=sha(log),resumed=initialized,new=len(new),cached=len(reuse),new_repeats=len(set(audit)&new),
        cached_repeats=len(set(audit)&reuse),different=sum(v!=answers[k] for k,v in audit.items()),seconds=time.perf_counter()-t))
    print("answers sealed",len(answers),len(audit),flush=True)

if __name__=="__main__":
    {"input":input_stage,"answer":answer_stage}[sys.argv[1]]()
