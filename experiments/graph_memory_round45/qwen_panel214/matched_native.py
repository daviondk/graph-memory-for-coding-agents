"""Guarantee input equality by applying the exact native /tokenize function independently to every example on CPU."""
from common import *
from matched_tokens import EXTRA,raw_text,INSTRUCTION,TAIL,CLI
from reference import tokenize
from concurrent.futures import ThreadPoolExecutor
from threading import local
def main():
    start=time.perf_counter();panel=read(OUT/"panel.json");rows=read(R34/"features.json.gz");sentences={};states={}
    def key(s):
        k=hashlib.sha256(s.encode()).hexdigest();sentences[k]=s;return k
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as f:
        for item in map(json.loads,f):
            q=item["state_id"]
            if q not in rows:continue
            cs=sorted(item["candidate_evidence"],key=lambda x:x["evidence_id"]);header="Instruct: "+INSTRUCTION+"\nQuery: "
            lead=[item.get(k) or "" for k in ("information_need","current_subgoal")];end=item.get("issue") or "";more=[raw_text(item[k]) for k in EXTRA if item.get(k)]
            states[q]=dict(three=key(header+"\n".join(lead+[end])),nine=key(header+"\n".join(lead+more+[end])),
               doc=[key(c["source_path"]+"\n"+c["content_excerpt"]) for c in cs],ids=[c["evidence_id"] for c in cs],seen=[int(c["observed_by_state"]) for c in cs])
    folder=CACHE/"runs-r40-tokenizer-cpu";folder.mkdir(exist_ok=True)
    listener=socket.socket();listener.bind(("127.0.0.1",0));port=listener.getsockname()[1];listener.close()
    args=[str(EXE),"-m",str(CACHE/NAME),"-dev","none","-ngl","0","--embeddings","--pooling","last","-t","1","-tb","1","-c","512","-b","32","-ub","32","-np","1",
          "--threads-http","4","--no-warmup","--offline","-lv","2","--host","127.0.0.1","--port",str(port)]
    url=f"http://127.0.0.1:{port}";stored={};thread=local()
    def get(pair):
        if not hasattr(thread,"session"):
            thread.session=requests.Session();thread.session.trust_env=False
        k,text=pair;tokens=tokenize(thread.session,url,text)
        return k,[len(tokens)+1,tokens[:511]+[TAIL]]
    with (folder/"server.log").open("wb") as log:
        proc=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES="-1"))
        try:
            with requests.Session() as sess:
                sess.trust_env=False
                for _ in range(75):
                    if proc.poll() is not None:raise RuntimeError("CPU tokenizer exited")
                    try:
                        if sess.get(url+"/health",timeout=1).ok:break
                    except requests.RequestException:pass
                    time.sleep(1)
                else:raise RuntimeError("CPU tokenizer unavailable")
            with ThreadPoolExecutor(max_workers=4) as pool:
                for k,v in pool.map(get,sorted(sentences.items())):stored[k]=v
        finally:proc.terminate();proc.wait(timeout=20)
    assert len(stored)==len(sentences)==25901
    prevpath=CACHE/"runs-r40-lexical-byte-input/matched-tokens.json.gz";previous=read(prevpath)
    assert previous["states"]==states
    mismatched=[k for k,v in stored.items() if v!=previous["tokens"][k]]
    previously=read(CACHE/"runs-r40-lexical-separator-preflight/matched-token-seal.json")
    save("matched-tokens.json.gz",dict(states=states,tokens=stored))
    save("matched-token-seal.json",dict(forecasts_input=sha(OUT/"matched-tokens.json.gz"),model=sha(CACHE/NAME),backend=sha(EXE),cli=sha(CLI),
        protocol=sha(OUT/"MATCHED_INPUT_RU.md"),program=sha(OUT/"matched_native.py"),canonical_tokenizer=sha(R39SRC/"reference.py"),
        states=len(states),unique_strings=len(stored),independent_native=len(stored),byte_io_crosscheck=len(stored)-len(mismatched),byte_io_disagrees=len(mismatched),
        prior_sha=sha(prevpath),prior_code=previously["program"],seconds=time.perf_counter()-start,requested_device="none"))
    print("Sealed individual native tokens for all",len(stored),"texts; corrected",len(mismatched),"batch encodings.")
if __name__=="__main__":main()
