"""Token-match all three policies, seal model-visible inputs, run an offline GPU reader."""
from prepare import *
import os,struct,time
sys.path.insert(0,str(HERE.parents[1]/"reranker"))
from common import EXE,READER,server
SYSTEM="Use the supplied documents to answer the question. Return only the shortest correct answer, with no explanation. If the documents do not establish the answer, return UNKNOWN."
PARAMS=dict(temperature=0,top_k=1,seed=460001,n_predict=96,cache_prompt=False,ignore_eos=False,stop=["\n"],stream=False)
def key(tokens):
    return hashlib.sha256(struct.pack(f"<{len(tokens)}I",*tokens)).hexdigest()
def main():
    import common
    common.RUN=RUN
    old=read(HERE.parents[2]/"graph_memory_round46/reader_transfer/plan.json")
    assert hashfile(READER)==old["model"] and hashfile(EXE)==old["server"]
    assert hashfile(RUN/"texts.json.gz")==load("texts-seal.json")["texts"]
    assert hashfile(HERE/"selection.json.gz")==load("registration.json")["selection"]
    data=read(RUN/"texts.json.gz");sel=load("selection.json.gz")
    with server(READER,["--parallel","1","--ctx-size","1024","--flash-attn","on","--threads","4"],"confirm-reader",18946) as (url,s,hw):
        assert hw["build"]==old["props"]["build_info"] and hw["slots"]==1 and hw["template_sha"]==old["chat_template"]
        def tokens(text,special=False):
            res=s.post(url+"/tokenize",json=dict(content=text,parse_special=special,add_special=False),timeout=45);res.raise_for_status();return res.json()["tokens"]
        marker=tokens("<|im_start|>system\n"+SYSTEM+"<|im_end|>\n<|im_start|>user\nQuestion: ",True)
        d1=tokens("\nDocument 1:\n");d2=tokens("\nDocument 2:\n");tail=tokens("<|im_end|>\n<|im_start|>assistant\n",True)
        tokenize=lambda ds:{j:tokens(t+"\n"+b)[:192] for j,(t,b) in ds.items()}
        first=tokenize(data["first"]);second=tokenize(data["second"])
        rows={};prompts={}
        for q,row in sel.items():
            a=first[str(row["seed"])];qs=tokens(data["questions"][q])[:80]
            pref=marker+qs+d1+a+d2
            cap=min(len(second[str(k)]) for k in row["second"].values())
            assert len(a)>0 and cap>0
            refs={}
            for arm,i in row["second"].items():
                seq=pref+second[str(i)][:cap]+tail;h=key(seq)
                assert len(seq)+96<=1024 and prompts.setdefault(h,seq)==seq
                refs[arm]=[i,h,len(seq)]
            assert len({v[2] for v in refs.values()})==1
            rows[q]=dict(first=row["seed"],first_tokens=len(a),second_tokens=cap,refs=refs)
        put("contexts.json.gz",rows);put("prompts.json.gz",prompts)
        put("input-seal.json",dict(prompts=hashfile(HERE/"prompts.json.gz"),contexts=hashfile(HERE/"contexts.json.gz"),
           texts=hashfile(HERE/"texts-seal.json"),selection=hashfile(HERE/"selection.json.gz"),
           params=PARAMS,reader=old["model"],server=old["server"],unique=len(prompts),hardware=hw,code=hashfile(Path(__file__))))
        # A fresh server has its own PID; the prompt hash permits restart without changing any visible input.
        print("Frozen unique reader inputs",len(prompts),flush=True)
        log=RUN/("answers-"+hashfile(HERE/"prompts.json.gz")+".jsonl");answers={}
        if log.exists():
            for line in log.read_bytes().splitlines():
                k,v=json.loads(line);assert k in prompts and k not in answers;answers[k]=v
        start=time.perf_counter()
        with log.open("a",encoding="utf-8") as f:
            for k,t in sorted(prompts.items()):
                if k in answers:continue
                res=s.post(url+"/completion",json=dict(PARAMS,prompt=t),timeout=120);res.raise_for_status();r=res.json()
                v=dict(answer=r["content"].strip(),tokens=r["tokens_predicted"],stop=r["stop_type"])
                answers[k]=v;f.write(json.dumps([k,v],ensure_ascii=False)+"\n");f.flush()
                if len(answers)%100==0:print(len(answers),"/",len(prompts),flush=True)
        assert set(answers)==set(prompts)
        put("answers.json.gz",answers)
        put("answer-seal.json",dict(inputs=hashfile(HERE/"input-seal.json"),answers=hashfile(HERE/"answers.json.gz"),
            unique=len(answers),wall_seconds=time.perf_counter()-start,model=old["model"]))
if __name__=="__main__":main()
