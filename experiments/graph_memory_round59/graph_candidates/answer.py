"""Generate one choice from actual candidate slates, never transfer answers between slates."""
from functools import lru_cache
import hashlib
import json
import re
import struct
import sys
from select_slates import HERE, OLD, get, put, sha

R52=HERE.parents[1]/"graph_memory_round52"
sys.path.insert(0,str(R52/"reranker"))
import common
PARAMS=dict(n_predict=8,temperature=0,top_k=1,seed=590113,cache_prompt=False,stream=False)


def key(seq):
    return hashlib.sha256(struct.pack(f"<{len(seq)}I",*seq)).hexdigest()


def main():
    seal=get(HERE/"selection-seal.json")
    assert all(sha(HERE/n)==h for n,h in seal["hashes"].items())
    assert sha(HERE/"PROTOCOL_RU.md")==seal["protocol"]
    roster=get(HERE/"roster.json.gz");slates=get(HERE/"slates.json.gz")
    docs={r["key"]:r for r in get(OLD/"cards.json")};eligible=set(roster["eligible_source_ids"])
    expected=get(R52/"global_answers/confirm/input-seal.json")
    assert common.sha(common.READER)==expected["reader"] and common.sha(common.EXE)==expected["server"]
    common.RUN=HERE
    with common.server(common.READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],"gpu",18959) as (url,session,hw):
        def post(name,args):
            r=session.post(url+"/"+name,json=args,timeout=120);r.raise_for_status();return r.json()
        @lru_cache(None)
        def tok(t,special=False):
            return post("tokenize",dict(content=t,parse_special=special,add_special=False))["tokens"]
        head=tok("<|im_start|>system\nChoose the earlier coding session most relevant to the new issue. The issues can share their root cause, implementation change or requested feature. Return one candidate number 1 through 5 and nothing else.<|im_end|>\n<|im_start|>user\nNew issue:\n",True)
        foot=tok("\nWhich prior session is related?<|im_end|>\n<|im_start|>assistant\n",True)
        blank=tok(" ");assert len(blank)==1
        @lru_cache(None)
        def card(k):
            v=docs[k]
            if k in eligible:
                seq=tok("Earlier issue: ")+tok(v["symptom"])[:95]+tok("\nOutcome: ")+tok(v["closure"])[:35]
            else:
                seq=tok("Historical text unavailable.")
            assert len(seq)<=150
            return seq+blank*(150-len(seq))
        prompts={};mapping={}
        for num,s in slates.items():
            pre=head+tok(roster["tasks"][num]["query"])[:450]
            info={}
            for a,items in s.items():
                order=sorted(items,key=lambda k:hashlib.sha256((num+"|"+k).encode()).digest())
                text=pre.copy()
                for j,k in enumerate(order,1):
                    text+=tok("\nCandidate "+str(j)+"\n")+card(k)
                text+=foot
                h=key(text)
                assert len(text)+PARAMS["n_predict"]<=4096 and prompts.setdefault(h,text)==text
                info[a]=dict(hash=h,order=order)
            assert len({len(prompts[p["hash"]]) for p in info.values()})==1
            mapping[num]=info
        put("inputs.json.gz",prompts);put("assignments.json.gz",mapping)
        put("prompt-seal.json",dict(params=PARAMS,model=expected["reader"],server=expected["server"],hardware=hw,
              hashes={n:sha(HERE/n) for n in ("answer.py","inputs.json.gz","assignments.json.gz","selection-seal.json")}))
        fp=sha(HERE/"inputs.json.gz")+expected["reader"]+expected["server"]+sha(HERE/"answer.py")
        ledger=HERE/"responses.jsonl";ans={}
        if ledger.exists():
            for ln in ledger.read_bytes().splitlines():
                f,h,v=json.loads(ln);assert f==fp;ans[h]=v
        print("Locked",len(prompts),"fresh requests for",len(mapping),"tasks",flush=True)
        for h,p in sorted(prompts.items()):
            if h in ans:continue
            v=post("completion",dict(PARAMS,prompt=p))
            ans[h]=dict(text=v["content"],output_tokens=v["tokens_predicted"],stop=v["stop_type"])
            with ledger.open("a",encoding="utf8") as f:print(json.dumps([fp,h,ans[h]]),file=f,flush=True)
        assert set(prompts)==set(ans)
        preds={}
        for q,arms in mapping.items():
            d={}
            for a,row in arms.items():
                s=ans[row["hash"]]["text"].strip();ok=bool(re.fullmatch("[1-5]",s))
                d[a]=dict(choice=row["order"][int(s)-1] if ok else slates[q][a][0],fallback=not ok)
            preds[q]=d
        put("answers.json.gz",ans);put("predictions.json.gz",preds)
        put("answer-seal.json",{n:sha(HERE/n) for n in ("answers.json.gz","predictions.json.gz","prompt-seal.json")})

if __name__=="__main__":main()
