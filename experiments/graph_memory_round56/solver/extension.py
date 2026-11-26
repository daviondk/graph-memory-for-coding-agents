"""Match recency capacity and separate direct-call evidence from candidate scope."""
from collections import Counter
import re
import sys
from generate import PARAMS, key, common
from study import *

MODELS=("file8","hash8","call_cascade","call_full","full_bm25")

def select():
    frozen=read("selections.json.gz");history=read("history.json.gz")
    out={}
    for q,r in frozen.items():
        task=r["task"];es=history[task["repo"]]["episodes"]
        scores=score_query(es,task)
        local=sorted({e["i"] for e in es if task["path"] in e["anchors"]})
        pool=list(range(len(es)))
        def ranked(indices):
            return min(indices,key=lambda j:(-scores[j],-es[j]["i"],es[j]["path"],es[j]["address"]))
        variants={"file8":r["evidence"]["file8"]["id"],"full_bm25":r["evidence"]["full_bm25"]["id"]}
        order=sorted(local,key=lambda i:digest((task["repo"]+"|"+task["path"]+"|"+history[task["repo"]]["commits"][i]).encode()))
        subset=set(order[:8])
        variants["hash8"]=ranked([j for j in pool if es[j]["i"] in subset] or pool)
        rx=re.compile(r"\b"+re.escape(task["name"])+r"\s*\(")
        valid={j for j,e in enumerate(es) if rx.search(e["text"])}
        stage="full_bm25"
        for name,indices in (("last_eight",{j for j in valid if es[j]["i"] in local[-8:]}),
                            ("all_local",{j for j in valid if es[j]["i"] in local}),("all_tests",valid)):
            if indices:
                choice=ranked(indices);stage=name;break
        else:choice=variants["full_bm25"]
        variants.update(call_cascade=choice,call_full=ranked(valid) if valid else variants["full_bm25"])
        out[q]=dict(ids=variants,stage=stage,total_direct=len(valid))
    write("extra-selections.json.gz",out)
    write("extra-selection-seal.json",dict(protocol=digest((HERE/"EXTENSION_RU.md").read_bytes()),
                  code=digest((HERE/"extension.py").read_bytes()),decisions=digest((HERE/"extra-selections.json.gz").read_bytes()),
                  primary_selection=digest((HERE/"selection-seal.json").read_bytes())))
def generate_extra():
    sel=read("extra-selections.json.gz");hist=read("history.json.gz");base=read("selections.json.gz")
    prior=read("prompts.json.gz");refs=read("assignments.json.gz");first=read("input-seal.json")
    old=read("answers.json.gz");assert set(old)==set(prior) and first["prompts"]==digest((HERE/"prompts.json.gz").read_bytes())
    common.RUN=RAW
    assert common.sha(common.READER)==first["model"] and common.sha(common.EXE)==first["server"]
    with common.server(common.READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],"call-reader",18956) as (url,s,hw):
        def tok(t,special=False):
            r=s.post(url+"/tokenize",json=dict(content=t,parse_special=special,add_special=False),timeout=30);r.raise_for_status()
            return r.json()["tokens"]
        end=tok("<|im_end|>\n<|im_start|>assistant\n",True)
        mark=tok("\nPreviously observed test source from this repository:\n")
        prompts={};assign={};visible={}
        for q,row in sel.items():
            task=base[q]["task"];es=hist[task["repo"]]["episodes"]
            orig=prior[refs[q]["contract"]["hash"]]
            assert orig[-len(end):]==end
            pre=orig[:-len(end)]
            pieces={}
            for arm,j in row["ids"].items():
                e=es[j]
                pieces[arm]=tok(e["path"]+" / "+e["address"]+"\n"+e["text"])
            width=min(refs[q]["file8"]["evidence"],*(len(v) for v in pieces.values()))
            assign[q]={};visible[q]={}
            for arm,part in pieces.items():
                seq=pre+mark+part[:width]+end;h=key(seq)
                assert prompts.setdefault(h,seq)==seq and (h not in prior or prior[h]==seq)
                assign[q][arm]=dict(hash=h,evidence=width,tokens=len(seq))
                r=s.post(url+"/detokenize",json={"tokens":part[:width]},timeout=30);r.raise_for_status()
                visible[q][arm]=r.json()["content"]
            assert len({v["tokens"] for v in assign[q].values()})==1
        write("extra-prompts.json.gz",prompts);write("extra-assignments.json.gz",assign);write("extra-visible.json.gz",visible)
        write("extra-input-seal.json",dict(registered=digest((HERE/"extra-selection-seal.json").read_bytes()),model=first["model"],
                  hardware=hw,params=PARAMS,hashes={f:digest((HERE/f).read_bytes()) for f in
                     ("extra-prompts.json.gz","extra-assignments.json.gz","extra-visible.json.gz")}))
        answers={h:old[h] for h in prompts if h in old};n_reused=len(answers)
        print("extra prompts",len(prompts),"including",n_reused,"identical cached",flush=True)
        log=RAW/("extra-"+digest((HERE/"extra-prompts.json.gz").read_bytes())+".jsonl")
        if log.exists():answers.update(dict(json.loads(x) for x in log.read_bytes().splitlines()))
        with log.open("a",encoding="utf8") as f:
            for h,ids in sorted(prompts.items()):
                if h in answers:continue
                resp=s.post(url+"/completion",json=dict(PARAMS,prompt=ids),timeout=110);resp.raise_for_status();v=resp.json()
                a=dict(text=v["content"],tokens=v["tokens_predicted"],stop=v["stop_type"])
                answers[h]=a;f.write(json.dumps([h,a],ensure_ascii=True)+"\n");f.flush()
        write("extra-answers.json.gz",answers)
        write("extra-answer-seal.json",dict(answers=digest((HERE/"extra-answers.json.gz").read_bytes()),n=len(answers),
                                       reused=n_reused,tokens_new=sum(r["tokens"] for h,r in answers.items() if h not in old)))
if __name__=="__main__":
    if sys.argv[1]=="select":select()
    elif sys.argv[1]=="generate":generate_extra()
    else:raise ValueError("expected select or generate")
