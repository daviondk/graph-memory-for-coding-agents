"""Extract exactly the visible 511 BPE tokens using the same GGUF on CPU; train/dev/test labels are closed."""
from common import *
from collections import defaultdict
import re,struct,tempfile
from reference import INSTRUCTION,TAIL
CLI=EXE.with_name("llama-tokenize.exe"); MARK="<|endoftext|>"; EXTRA=("current_observation","current_hypothesis","search_queries","opened_files","latest_test_output","current_diff")
def specials(path):
    with path.open("rb") as f:
        assert f.read(4)==b"GGUF";version,_,count=struct.unpack("<IQQ",f.read(20));assert version==3
        fixed={0:"B",1:"b",2:"H",3:"h",4:"I",5:"i",6:"f",7:"?",10:"Q",11:"q",12:"d"}
        def string():return f.read(struct.unpack("<Q",f.read(8))[0])
        found={}
        def value(t,keep):
            if t==8:
                x=string();return x.decode("utf8",errors="replace") if keep else None
            if t==9:
                kind,n=struct.unpack("<IQ",f.read(12))
                if not keep and kind in fixed:f.seek(struct.calcsize("<"+fixed[kind])*n,1);return
                vals=[value(kind,keep) for _ in range(n)]
                return vals if keep else None
            fmt="<"+fixed[t];s=f.read(struct.calcsize(fmt));return struct.unpack(fmt,s)[0] if keep else None
        for _ in range(count):
            key=string().decode();t=struct.unpack("<I",f.read(4))[0];want=key in ("tokenizer.ggml.token_type","tokenizer.ggml.tokens")
            v=value(t,want)
            if want:found[key]=v
        words=found["tokenizer.ggml.tokens"];types=found["tokenizer.ggml.token_type"];assert len(words)==len(types) and words[TAIL]==MARK
        return [w for w,t in zip(words,types) if t in (2,3,4) and w]
def ids(text,parsing):
    argv=[str(CLI),"-m",str(CACHE/NAME),"--ids","--no-bos","--no-escape","--offline","-dev","none","-ngl","0"]
    if not parsing:argv.append("--no-parse-special")
    with tempfile.TemporaryDirectory(dir=CACHE) as scratch:
        source=Path(scratch)/"input.bin";source.write_bytes(text.encode())
        p=subprocess.run([*argv,"-bf",str(source)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    return json.loads(p.stdout)
def raw_text(v):return v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,separators=(",",":"))
def main():
    assert sha(OUT/"MATCHED_INPUT_RU.md")=="b2b3a613297f488baca2897c8e8a65204c3ccd3bde0509a29757cba9a31d0092"
    start=time.perf_counter();rows=read(R34/"features.json.gz");sentences={};states={}
    def remember(s):
        k=hashlib.sha256(s.encode()).hexdigest()
        if k not in sentences:sentences[k]=s
        return k
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as fi:
        for item in map(json.loads,fi):
            q=item["state_id"]
            if q not in rows:continue
            candidates=sorted(item["candidate_evidence"],key=lambda c:c["evidence_id"]);head="Instruct: "+INSTRUCTION+"\nQuery: "
            lead=[item.get(k) or "" for k in ("information_need","current_subgoal")];end=item.get("issue") or ""
            more=[raw_text(item[k]) for k in EXTRA if item.get(k)]
            states[q]=dict(three=remember(head+"\n".join(lead+[end])),nine=remember(head+"\n".join(lead+more+[end])),
                doc=[remember(c["source_path"]+"\n"+c["content_excerpt"]) for c in candidates],
                ids=[c["evidence_id"] for c in candidates],seen=[int(c["observed_by_state"]) for c in candidates])
    assert len(states)==494
    special=specials(CACHE/NAME);test=re.compile("|".join(re.escape(t) for t in sorted(special,key=len,reverse=True)));pack=[];byte_count=0;stored={};distinct_fallback=0
    def record(k,v):stored[k]=[len(v)+1,(v[:511]+[TAIL])]
    def flush():
        if not pack:return
        joined=MARK.join(sentences[k] for k in pack)+MARK
        vals=ids(joined,True);chunks=[];cur=[]
        for tok in vals:
            if tok==TAIL:chunks.append(cur);cur=[]
            else:cur.append(tok)
        assert len(chunks)==len(pack) and not cur
        for k,v in zip(pack,chunks):record(k,v)
        pack.clear()
    for k,s in sorted(sentences.items()):
        if test.search(s) or "\x1a" in s or "\x00" in s:
            record(k,ids(s,False));distinct_fallback+=1;continue
        if byte_count+len(s.encode())>900000:flush();byte_count=0
        pack.append(k);byte_count+=len(s.encode())
    flush()
    deterministic=sorted(sentences,key=lambda k:hashlib.sha256(("r40/token-audit/"+k).encode()).digest())[:32]
    for k in deterministic:
        isolated=ids(sentences[k],False);assert stored[k]==[len(isolated)+1,isolated[:511]+[TAIL]]
    assert set(stored)==set(sentences)
    save("matched-tokens.json.gz",dict(states=states,tokens=stored))
    save("matched-token-seal.json",dict(forecasts_input=sha(OUT/"matched-tokens.json.gz"),model=DIGEST,cli=sha(CLI),protocol=sha(OUT/"MATCHED_INPUT_RU.md"),
            program=sha(OUT/"matched_tokens.py"),states=len(states),unique_strings=len(stored),isolated=distinct_fallback,exact_individual=deterministic,
            observed_special_spellings=len(special),seconds=time.perf_counter()-start))
    print("Sealed",len(stored),"unique input token vectors across",len(states),"states.")
if __name__=="__main__":main()
