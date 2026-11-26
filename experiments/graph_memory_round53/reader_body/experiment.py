"""Replace document bodies while preserving exact visible titles and per-question reader budgets."""
from pathlib import Path
import hashlib,gzip,json,struct,sys,time,unicodedata
from zipfile import ZipFile
D=Path(__file__).resolve().parent
EXP=D.parents[1];R52=EXP/"graph_memory_round52"
PREV=R52/"global_answers/confirm/supplement"
ORIGINAL=Path("D:/CodexResearch/x20-r52-global-supp-reader/texts.json.gz")
CACHE=Path("D:/CodexResearch/x20-r50-qa-external")
sys.path.insert(0,str(R52/"reranker"))
import common
from common import read,save,sha,EXE,READER,server
PARAMS=dict(temperature=0,top_k=1,seed=460001,n_predict=96,cache_prompt=False,ignore_eos=False,stop=["\n"],stream=False)
ARMS=("learned_href","learned_literal")
def key(xs):return hashlib.sha256(struct.pack(f"<{len(xs)}I",*xs)).hexdigest()
def put(n,z):save(D/n,z)
def get(n):return read(D/n)
def canon(s):return unicodedata.normalize("NFKC"," ".join(s.replace("_"," ").split())).casefold()
def disallowed(qids):
    src=read(EXP/"graph_memory_round50/qa_external/official-source.json")
    archive=CACHE/"data_ids.zip"
    assert sha(archive)==src["archive"]
    sys.path.insert(0,str(EXP/"graph_memory_round50/adaptive_address"))
    from stream_json import iter_array
    with ZipFile(archive) as z,z.open("data_ids/train.json") as f:
        return {r["_id"]:{canon(name) for name,_sentences in r["context"]} for r in iter_array(f) if r["_id"] in qids}
def main():
    prev=read(PREV/"contexts.json.gz");prev={q.split("|",1)[1]:r for q,r in prev.items() if q.startswith("fallback|")}
    old=read(PREV/"input-seal.json");orig=read(PREV/"prompts.json.gz")
    assert len(prev)==512 and sha(PREV/"contexts.json.gz")==old["contexts"] and sha(PREV/"prompts.json.gz")==old["prompts"]
    assert sha(ORIGINAL)==read(PREV/"texts-seal.json")["texts"] and old["reader"]==sha(READER) and old["server"]==sha(EXE)
    assert old["params"]==PARAMS
    raw=read(ORIGINAL)
    forbidden=disallowed(set(prev));assert set(forbidden)==set(prev)
    other=read(PREV.parent/"selection.json.gz")
    assert sha(PREV.parent/"selection.json.gz")==read(PREV.parent/"registration.json")["selection"]
    put("registration.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),script=sha(Path(__file__)),prior_input=sha(PREV/"input-seal.json"),
        prior_options=sha(PREV.parent/"selection.json.gz"),prior_source=sha(ORIGINAL),n=len(prev)))
    common.RUN=D
    with server(READER,["--parallel","1","--ctx-size","1024","--flash-attn","on","--threads","4"],"gpu",18953) as (url,s,hw):
        assert hw["build"]==old["hardware"]["build"] and hw["template_sha"]==old["hardware"]["template_sha"]
        def encode(txt,special=False):
            r=s.post(url+"/tokenize",json=dict(content=txt,parse_special=special,add_special=False),timeout=60);r.raise_for_status();return r.json()["tokens"]
        tail=encode("<|im_end|>\n<|im_start|>assistant\n",True)
        docs={int(k):(t,b) for k,(t,b) in raw["second"].items()}
        pool=sorted({i for r in prev.values() for i,_,_ in r["refs"].values()})
        # Excluded labels come from entire author candidate context, not supporting facts or scoring.
        tokenized={i:dict(title=encode(docs[i][0]+"\n"),body=encode(docs[i][1])[:192],
                   real=encode(docs[i][0]+"\n"+docs[i][1])[:192]) for i in pool}
        contexts={};prompts={};changed_bounds=0;clipped=0;donor_checks={}
        for q,r in sorted(prev.items()):
            width=r["second_tokens"]
            ids={r["refs"][a][0] for a in ARMS}
            foreign=set(other[q]["second"].values())|ids|{r["first"]}
            # No own first/second article, and no authors' true or distractor article for this question.
            banned=forbidden[q]|{canon(raw["first"][str(r["first"])][0])}|{canon(docs[i][0]) for i in ids}
            need=max(width-min(width,len(tokenized[i]["title"])) for i in ids)
            eligible=[i for i in pool if i not in foreign and canon(docs[i][0]) not in banned and len(tokenized[i]["body"])>=need]
            donor=min(eligible,key=lambda i:hashlib.sha256((f"r53-donor-v1|{q}|{i}").encode()).hexdigest())
            donor_checks[q]=dict(donor=donor,n_forbidden_titles=len(banned),eligible=len(eligible))
            refs={};head_lengths={};retok=[]
            for arm in ARMS:
                i,oldkey,n=r["refs"][arm];seq=orig[oldkey];assert key(seq)==oldkey and seq[-len(tail):]==tail
                real=seq[-len(tail)-width:-len(tail)]
                assert real==tokenized[i]["real"][:width]
                header=tokenized[i]["title"][:width]
                if len(tokenized[i]["title"])>width:clipped+=1
                if real[:len(header)]!=header:
                    changed_bounds+=1;retok.append(arm)
                new=seq[:len(seq)-len(tail)-width]+header+tokenized[donor]["body"][:width-len(header)]+tail
                assert len(seq)==len(new)==n;h=key(new)
                assert prompts.setdefault(h,new)==new
                refs[arm]=[i,h,n];head_lengths[arm]=len(header)
            assert len({v[2] for v in refs.values()})==1
            if len(ids)==1:assert len({v[1] for v in refs.values()})==1
            contexts[q]=dict(first=r["first"],second_tokens=width,refs=refs,header=head_lengths,retokenized=retok,donor=donor)
        put("contexts.json.gz",contexts);put("prompts.json.gz",prompts);put("donors.json.gz",donor_checks)
        put("input-seal.json",dict(contexts=sha(D/"contexts.json.gz"),prompts=sha(D/"prompts.json.gz"),
            donors=sha(D/"donors.json.gz"),registration=sha(D/"registration.json"),n_unique=len(prompts),hardware=hw,
            clipped_assignments=clipped,retokenized_boundaries=changed_bounds,model=old["reader"],params=PARAMS))
        print("Sealed",len(prompts),"unique inputs; cutoff headers",clipped,"retokenized",changed_bounds,flush=True)
        log=D/("answers-"+sha(D/"prompts.json.gz")+".jsonl");answers={}
        if log.exists():
            for line in log.read_bytes().splitlines():
                h,v=json.loads(line);assert h in prompts and h not in answers;answers[h]=v
        tic=time.perf_counter()
        with log.open("a",encoding="utf-8") as f:
            for h,seq in sorted(prompts.items()):
                if h in answers:continue
                r=s.post(url+"/completion",json=dict(PARAMS,prompt=seq),timeout=120);r.raise_for_status();v=r.json()
                item=dict(answer=v["content"].strip(),tokens=v["tokens_predicted"],stop=v["stop_type"])
                answers[h]=item;f.write(json.dumps([h,item],ensure_ascii=False)+"\n");f.flush()
                if len(answers)%100==0:print(len(answers),"/",len(prompts),flush=True)
        assert set(answers)==set(prompts)
        put("answers.json.gz",answers);put("answer-seal.json",dict(answers=sha(D/"answers.json.gz"),input=sha(D/"input-seal.json"),
            run_seconds=time.perf_counter()-tic,model=old["reader"],unique=len(answers)))
if __name__=="__main__":main()
