"""Build and seal the same visible pre-fix prompt budget, then generate complete methods."""
import os,struct,time
from study import *
sys.path.insert(0,str(R52/"reranker"))
from common import EXE,READER,server
PARAMS=dict(temperature=0,top_k=1,seed=540271,n_predict=384,cache_prompt=False,ignore_eos=False,stream=False)
def key(xs):return hash_bytes(struct.pack(f"<{len(xs)}I",*xs))
def main():
    import common
    common.RUN=WORK
    data=get("observations.json.gz");sel=get("selection.json")
    assert sha(D/"observations.json.gz")==sel["observations"] and sha(D/"PROTOCOL_RU.md")==sel["protocol"]
    prev=common.read(R52/"global_answers/confirm/input-seal.json")
    assert sha(READER)==prev["reader"] and sha(EXE)==prev["server"]
    with server(READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],"class-reader",18954) as (url,s,hw):
        assert hw["build"]==prev["hardware"]["build"] and hw["template_sha"]==prev["hardware"]["template_sha"]
        def tokens(txt,special=False):
            r=s.post(url+"/tokenize",json=dict(content=txt,parse_special=special,add_special=False),timeout=40);r.raise_for_status();return r.json()["tokens"]
        header=tokens("<|im_start|>system\nYou maintain a Python class. Implement only the requested method using its public contract and available class information. Return exactly one complete Python method definition. Do not include any explanation, tests or Markdown.<|im_end|>\n<|im_start|>user\n",True)
        mark=tokens("\n\nObservation from another method in the same class:\n")
        end=tokens("<|im_end|>\n<|im_start|>assistant\n",True)
        contexts={};prompts={}
        for q,r in sorted(data.items()):
            pref=header+tokens("Existing imports: "+"; ".join(r["imports"])+"\n"+r["task"])
            parts={k:tokens(src) for k,src in r["evidence"].items()};width=min(192,*map(len,parts.values()))
            assert width>0
            refs={}
            for arm in ARMS:
                if arm=="contract":seq=pref+end;choose=None
                else:choose=r["choices"][arm];seq=pref+mark+parts[choose][:width]+end
                h=key(seq);assert len(seq)+384<=4096 and prompts.setdefault(h,seq)==seq
                refs[arm]=[choose,h,len(seq)]
            assert refs["caller_bm25"][2]==refs["bm25"][2]
            contexts[q]=dict(cls=r["cls"],width=width,refs=refs)
        put("contexts.json.gz",contexts);put("prompts.json.gz",prompts)
        put("input-seal.json",dict(selection=sha(D/"selection.json"),contexts=sha(D/"contexts.json.gz"),prompts=sha(D/"prompts.json.gz"),
            n=len(data),unique=len(prompts),params=PARAMS,model=prev["reader"],server=prev["server"],hardware=hw,code=sha(Path(__file__))))
        log=WORK/("output-"+sha(D/"prompts.json.gz")+".jsonl");answers={}
        if log.exists():
            for ln in log.read_bytes().splitlines():
                h,r=json.loads(ln);assert h in prompts and h not in answers;answers[h]=r
        print("Sealed",len(prompts),"native prompts for",len(contexts),"methods",flush=True)
        tic=time.perf_counter()
        with log.open("a",encoding="utf-8") as f:
            for h,seq in sorted(prompts.items()):
                if h in answers:continue
                r=s.post(url+"/completion",json=dict(PARAMS,prompt=seq),timeout=120);r.raise_for_status();v=r.json()
                a=dict(code=v["content"],tokens=v["tokens_predicted"],stop=v["stop_type"])
                answers[h]=a;f.write(json.dumps([h,a],ensure_ascii=False)+"\n");f.flush()
                if len(answers)%25==0:print(len(answers),"/",len(prompts),flush=True)
        assert set(answers)==set(prompts)
        put("answers.json.gz",answers);put("answer-seal.json",dict(answers=sha(D/"answers.json.gz"),inputs=sha(D/"input-seal.json"),
           wall_seconds=time.perf_counter()-tic,n=len(answers),generated_tokens=sum(a["tokens"] for a in answers.values())))
if __name__=="__main__":main()
