"""Prepare matched input tokens, reuse identical reader outputs and generate missing inputs on the RTX 3090."""
import struct
from common import *

PARAMS=dict(temperature=0,top_k=1,seed=460001,n_predict=96,cache_prompt=False,ignore_eos=False,stop=["\n"],stream=False)
def h(t):
    return hashlib.sha256(struct.pack(f"<{len(t)}I",*t)).hexdigest()
def archive():
    known={}
    for path in [PANELS[p][0]/"answers.json.gz" for p in EVAL]+[R51/f for f in ("baseline/new-answers.json.gz","baseline/confirm/new-answers.json.gz","frozen_ablation/new-answers.json.gz")]:
        for k,v in read(path).items():assert known.setdefault(k,v)==v
    return known
def caps():
    two=read(R51/"baseline/matched-contexts.json.gz")["gate_confirmation"];hot=read(R51/"baseline/confirm/contexts.json.gz")
    return {"2wiki":{q:r["n"] for q,r in two.items()},"hotpot":{q:r["cap"] for q,r in hot.items()}}
def selected_inputs(s,url,choices,known):
    ctx={};queue={};checks={};old_caps=caps()
    token_cache={}
    for p in EVAL:
        src,local=PANELS[p];base=read(src/"contexts.json.gz");raw=read(src/"prompts.json.gz")
        assert set(raw)==set(read(src/"answers.json.gz")) and all(h(t)==k for k,t in raw.items())
        assert sha(local/"visible.json.gz")==read(src/"panel.json")["visible"]
        catalog=read(local/"visible.json.gz");tail=read(src/"reader-boundaries.json")["tail"];ctx[p]={}
        for k in sorted(raw,key=lambda k:hashlib.sha256(("r52-qa-replay|"+k).encode()).hexdigest())[:12]:checks[k]=raw[k]
        for q,items in choices[p].items():
            old=base[q];n=old["n"];prev=old_caps[p][q]
            assert 0<prev<=n
            oldkey=old["refs"]["dense"][1];prefix=raw[oldkey][:-(n+len(tail))]
            saved={i:raw[k][len(prefix):-len(tail)] for i,k,L in old["refs"].values()}
            for i,k,L in old["refs"].values():assert prefix+saved[i]+tail==raw[k] and len(saved[i])==n
            extra=set(items.values())-set(saved)
            if extra:
                cats={i:t+"\n"+b for i,t,b in catalog[q][1]}
                for i in extra:
                    txt=cats[i]
                    if txt not in token_cache:
                        r=s.post(url+"/tokenize",json=dict(content=txt,parse_special=False,add_special=False),timeout=30);r.raise_for_status()
                        token_cache[txt]=r.json()["tokens"][:192]
                    saved[i]=token_cache[txt]
            width=min(prev,min(len(saved[i]) for i in items.values()))
            refs={}
            for a,i in items.items():
                tokens=prefix+saved[i][:width]+tail;k=h(tokens)
                assert i!=old["seed"]
                if k not in known:assert queue.setdefault(k,tokens)==tokens
                refs[a]=[i,k,len(tokens)]
            assert len({v[2] for v in refs.values()})==1
            ctx[p][q]=dict(seed=old["seed"],cluster=old["cluster"],previous=prev,cap=width,prefix=h(prefix),refs=refs)
        assert len({v["cluster"] for v in ctx[p].values()})==len(ctx[p])
    put("contexts.json.gz",ctx);put("new-prompts.json.gz",queue)
    put("input-seal.json",dict(contexts=sha(D/"contexts.json.gz"),prompts=sha(D/"new-prompts.json.gz"),
        decisions=sha(D/"decision-seal.json"),params=PARAMS,replay=sorted(checks),code=sha(Path(__file__))))
    return queue,checks

def main():
    old=read(R50.parent/"graph_memory_round46/reader_transfer/plan.json")
    assert sha(READER)==old["model"] and sha(EXE)==old["server"]
    assert sha(D/"choices.json.gz")==get("decision-seal.json")["choices"]
    choices=get("choices.json.gz");known=archive()
    with server(READER,["--parallel","1","--ctx-size","1024","--flash-attn","on","--threads","4"],"reader",18935) as (url,s,hw):
        assert hw["build"]==old["props"]["build_info"] and hw["slots"]==1 and hw["template_sha"]==old["chat_template"]
        queue,checks=selected_inputs(s,url,choices,known);print("Sealed",len(queue),"new reader prompts",flush=True)
        def one(tokens):
            r=s.post(url+"/completion",json=dict(PARAMS,prompt=tokens),timeout=120);r.raise_for_status();v=r.json()
            return dict(answer=v["content"].strip(),tokens=v["tokens_predicted"],stop=v["stop_type"])
        check={}
        for k,t in sorted(checks.items()):
            check[k]=one(t);assert check[k]==known[k]
        put("reader-replay.json",check)
        start=time.perf_counter();answers={}
        f=RUN/("answers-"+sha(D/"input-seal.json")+".jsonl")
        if f.exists():
            for line in f.read_bytes().splitlines():
                k,v=json.loads(line);answers[k]=v
        with f.open("a",encoding="utf8") as journal:
            for k,t in sorted(queue.items()):
                if k in answers:continue
                answers[k]=one(t);journal.write(json.dumps([k,answers[k]],ensure_ascii=False)+"\n")
                if len(answers)%50==0:journal.flush();print(len(answers),"/",len(queue),flush=True)
        assert set(answers)==set(queue)
        put("new-answers.json.gz",answers)
        put("answer-seal.json",dict(answers=sha(D/"new-answers.json.gz"),inputs=sha(D/"input-seal.json"),
            checks=sha(D/"reader-replay.json"),replayed=len(check),unique=len(answers),seconds=time.perf_counter()-start,server=hw,model=old["model"]))
if __name__=="__main__":main()

