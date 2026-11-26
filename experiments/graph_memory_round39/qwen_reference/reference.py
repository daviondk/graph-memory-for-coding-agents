"""Run Qwen3-Embedding on CPU inside the machine and seal predictions before scoring."""
from panel import *
from fetch import CACHE, DIGEST, NAME
import base64
from collections import Counter
import os
import socket
import subprocess
import time
import numpy as np
import requests

EXE = Path("D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe")
RUN = CACHE/"runs-r39-panel-v1"
INSTRUCTION = "Given a coding agent's current state, retrieve source evidence needed for its next decision."
TAIL = 151643  # The HF embedding tokenizer's single-sequence postprocessor adds <|endoftext|>.


def tokenize(session, base, text):
    response = session.post(base+"/tokenize",json={"content":text,"add_special":False,"parse_special":False},timeout=35)
    response.raise_for_status()
    return response.json()["tokens"]


def embed(session, base, batch):
    answer = session.post(base+"/v1/embeddings", json={"input":batch,"encoding_format":"base64"},timeout=600)
    answer.raise_for_status()
    vecs = []
    for row in sorted(answer.json()["data"],key=lambda d:d["index"]):
        value = row["embedding"]
        vector = np.frombuffer(base64.b64decode(value),"<f4") if isinstance(value,str) else np.asarray(value, np.float32)
        assert vector.shape == (4096,) and np.isfinite(vector).all()
        vecs.append(vector/max(np.linalg.norm(vector),1e-12))
    assert len(vecs)==len(batch)
    return np.stack(vecs)


def process_state(session, base, item):
    started = time.perf_counter()
    query = "Instruct: "+INSTRUCTION+"\nQuery: "+"\n".join(item.get(key) or "" for key in ("information_need","current_subgoal","issue"))
    candidates = sorted(item["candidate_evidence"],key=lambda c:c["evidence_id"])
    texts = [query] + [c["source_path"]+"\n"+c["content_excerpt"] for c in candidates]
    tok = [tokenize(session,base,t) for t in texts]
    lengths = [len(t)+1 for t in tok]
    clipped = [t[:511]+[TAIL] for t in tok]
    orders = sorted(range(len(tok)), key=lambda j:len(clipped[j]))
    matrix = np.empty((len(tok),4096),np.float32)
    for k in range(0,len(orders),4):
        sl = orders[k:k+4]
        matrix[sl]=embed(session,base,[clipped[j] for j in sl])
    scores = (matrix[1:] @ matrix[0]).astype(float)
    ids = [c["evidence_id"] for c in candidates]
    seen = np.array([c["observed_by_state"] for c in candidates],float)
    top = lambda vals: [ids[i] for i in np.argsort(-vals,kind="stable")[:8]]
    return dict(ranks={"qwen":top(scores),"qwen_seen":top(scores-1e5*seen)},
                scores=dict(zip(ids,scores.tolist())),lengths=lengths,
                tokens=sum(map(len,clipped)),truncated=sum(x>512 for x in lengths),seconds=time.perf_counter()-started)


def main():
    panel = read(ROOT/"panel.json")
    expected = panel["states"]
    assert sha(ROOT/"PROTOCOL_RU.md")==panel["protocol"]
    assert sha(CACHE/NAME)==DIGEST
    RUN.mkdir(exist_ok=True)
    states = {}
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as stream:
        for row in map(json.loads,stream):
            if row["state_id"] in expected:
                states[row["state_id"]] = row
    assert states.keys()==expected.keys()
    s = socket.socket()
    s.bind(("127.0.0.1",0))
    port=s.getsockname()[1]
    s.close()
    args = [str(EXE),"-m",str(CACHE/NAME),"-dev","none","-ngl","0","--embeddings","--pooling","last",
            "-c","4096","-b","2048","-ub","512","-t","6","-tb","6","-np","4","--host","127.0.0.1","--port",str(port),"--no-warmup"]
    session = requests.Session()
    session.trust_env=False
    base = "http://127.0.0.1:"+str(port)
    log = (RUN/"server.log").open("wb")
    env=dict(os.environ, CUDA_VISIBLE_DEVICES="-1")
    child=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
    fingerprint = {p:sha(ROOT/p) for p in ("panel.json","reference.py","PROTOCOL_RU.md")}
    fingerprint["model"]=DIGEST
    fingerprint["runtime"]=sha(EXE)
    results = {}
    try:
        for attempt in range(90):
            if child.poll() is not None:
                raise RuntimeError("llama-server failed to start; see local server.log")
            try:
                if session.get(base+"/health",timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("local CPU embeddings server")
        for q in sorted(expected,key=lambda q:expected[q]["position"]):
            name = RUN/(hashlib.sha256(q.encode()).hexdigest()+".json")
            if name.exists():
                cached=read(name)
                assert cached["sign"]==fingerprint
                value=cached["data"]
            else:
                value=process_state(session,base,states[q])
                cached={"sign":fingerprint,"state_id":q,"data":value}
                name.write_text(json.dumps(cached,sort_keys=True)+"\n",encoding="utf8")
            results[q]=value
            print("states",len(results),"of",len(expected),"candidates",len(value["scores"]),"tokens",value["tokens"],
                  "seconds",round(value["seconds"],1),flush=True)
    finally:
        child.terminate()
        child.wait(timeout=20)
        log.close()
    write("qwen-reference.json",results)
    write("forecast-seal.json",{"inputs":fingerprint,"reference":sha(ROOT/"qwen-reference.json"),
                                "hardware":"AMD Ryzen 7 8700F CPU, 6 threads, no GPU","llama_flags":args[3:]})


if __name__ == "__main__":
    main()
