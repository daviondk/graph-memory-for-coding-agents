"""Lock same-slate prompts then issue greedy reader requests in hash order."""
from functools import lru_cache
import hashlib
import json
import re
import struct
import sys
from roster import HERE, OLD, STAGE, get, put, sha
R52=HERE.parents[1]/"graph_memory_round52"
sys.path.insert(0,str(R52/"reranker"))
import common

ARMS=("true","rotation","flat")
PARAMS=dict(n_predict=8,temperature=0,top_k=1,seed=590113,cache_prompt=False,stream=False)


def key(xs):
    return hashlib.sha256(struct.pack(f"<{len(xs)}I",*xs)).hexdigest()


def shifted(edges):
    if not edges:
        return []
    targets=[b for _,b in edges]
    return [[a,targets[(i+1)%len(edges)]] for i,(a,_) in enumerate(edges)]


def main():
    reg=get(HERE/"graph-seal.json")
    assert all(reg[k]==sha(HERE/n) for k,n in (("protocol","PROTOCOL_RU.md"),("graph","graph.json.gz"),("cohort","cohort.json.gz")))
    c=get(HERE/"cohort.json.gz");idx=get(HERE/"graph.json.gz");rank=get(OLD/"blind_ranks.json")
    cards={v["key"]:v for v in get(OLD/"cards.json")}
    assert sha(OLD/"cards.json")==reg["original_cards"]
    expected=get(R52/"global_answers/confirm/input-seal.json")
    assert common.sha(common.READER)==expected["reader"] and common.sha(common.EXE)==expected["server"]
    common.RUN=HERE
    with common.server(common.READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],
                       "gpu",18959) as (url,s,hw):
        def post(ep,payload):
            r=s.post(url+"/"+ep,json=payload,timeout=120)
            r.raise_for_status()
            return r.json()
        @lru_cache(None)
        def tok(t,special=False):
            return post("tokenize",dict(content=t,parse_special=special,add_special=False))["tokens"]
        intro=tok("<|im_start|>system\nChoose the one earlier coding session most relevant to the new issue. An earlier issue can share its cause, change or feature. Read nodes R and edit nodes E refer to files in the same old session. R>E links report tool activity. Return only the candidate number 1, 2, 3, 4 or 5. Do not explain.<|im_end|>\n<|im_start|>user\nNew issue:\n",True)
        end=tok("\nWhich earlier session is related?<|im_end|>\n<|im_start|>assistant\n",True)
        blank=tok(" ")
        assert len(blank)==1
        packets={}
        for step,k in enumerate(cards):
            if k not in idx:
                q=tok("Historical text unavailable.\n")
                packets[k]={a:q for a in ARMS}
                continue
            c0=cards[k];g=idx[k]
            q=tok("Historical issue: ")+tok(c0["symptom"])[:95]+tok("\nHistorical outcome: ")+tok(c0["closure"])[:35]
            for prefix,paths in (("R",g["src"]),("E",g["dst"])):
                for number,p in enumerate(paths,1):
                    q+=tok("\n"+prefix+str(number)+" ")+tok(p)[-15:]
                    if prefix=="E" and g["hints"][p]:
                        q+=tok(" ")+tok(" ".join(g["hints"][p]))[:15]
            mark=tok("\nLinks: ")
            choices={"true":g["edges"],"rotation":shifted(g["edges"]),"flat":[]}
            def serialize(e):
                return tok(" ".join("R"+str(a)+">E"+str(b) for a,b in sorted(e))) if e else []
            fields={a:serialize(e) for a,e in choices.items()}
            m=max(map(len,fields.values()))
            packets[k]={a:q+mark+v+blank*(m-len(v))+tok("\n") for a,v in fields.items()}
        # Avoid accidental mutation of shared lists in the token-cache.
        prompts={};assign={}
        for num,task in c["tasks"].items():
            r=rank[int(num)]
            assert int(num)==r["ordinal"]
            base=r["fusion"][:5]
            assert len(base)==len(set(base))==5
            order=sorted(base,key=lambda x:hashlib.sha256((num+"|"+x).encode()).digest())
            out={}
            for a in ARMS:
                ids=intro+tok(task["query"])[:450]
                for j,k in enumerate(order,1):
                    ids+=tok("\nCandidate "+str(j)+"\n")+packets[k][a]
                ids+=end
                h=key(ids);assert prompts.setdefault(h,ids)==ids and len(ids)+PARAMS["n_predict"]<=4096
                out[a]=h
            assert len({len(prompts[x]) for x in out.values()})==1
            assign[num]=dict(base=base,order=order,arms=out)
        put("assignments.json.gz",assign);put("inputs.json.gz",prompts)
        put("prompt-seal.json",dict(hashes={n:sha(HERE/n) for n in ("PROTOCOL_RU.md","graph-seal.json","assignments.json.gz","inputs.json.gz","run.py")},
               model=expected["reader"],server=expected["server"],params=PARAMS,hardware=hw,baseline=sha(OLD/"blind_ranks.json")))
        ans={};log=HERE/"responses.jsonl"
        fingerprint=sha(HERE/"inputs.json.gz")+expected["reader"]+expected["server"]+sha(HERE/"run.py")
        if log.exists():
            for ln in log.read_bytes().splitlines():
                f,h,v=json.loads(ln);assert f==fingerprint;ans[h]=v
        print("Sealed",len(assign),"queries and",len(prompts),"unique inputs",flush=True)
        for h,p in sorted(prompts.items()):
            if h in ans:continue
            resp=post("completion",dict(PARAMS,prompt=p))
            v=dict(text=resp["content"],output_tokens=resp["tokens_predicted"],stop=resp["stop_type"])
            with log.open("a",encoding="utf8") as writer:
                print(json.dumps([fingerprint,h,v]),file=writer,flush=True)
            ans[h]=v
            if len(ans)%40==0:print("Completed",len(ans),"/",len(prompts),flush=True)
        assert set(prompts)==set(ans)
        scores={}
        for num,r in assign.items():
            row={}
            for a,h in r["arms"].items():
                s0=ans[h]["text"].strip()
                valid=bool(re.fullmatch("[1-5]",s0))
                row[a]=dict(selected=r["order"][int(s0)-1] if valid else r["base"][0],fallback=not valid)
            scores[num]=row
        put("answers.json.gz",ans);put("predictions.json.gz",scores)
        put("answer-seal.json",{n:sha(HERE/n) for n in ("prompt-seal.json","predictions.json.gz","answers.json.gz")})


if __name__=="__main__":main()
