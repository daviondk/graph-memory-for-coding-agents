import base64,gzip,socket,subprocess,time
import numpy as np
import requests
from paths_a import *

INSTRUCTION="Given a question and a passage already read, retrieve the title of the next passage needed to answer the question."
END=151643

def main():
    check();src=get(D/"projection-seal.json");assert sha(P/"catalog-input.json.gz")==src["visible"]
    inputs=get(P/"catalog-input.json.gz");rows={};titles={};queries={}
    for q,(question,snippet,candidates) in inputs.items():
        query="Instruct: "+INSTRUCTION+"\nQuery: "+question+"\n"+snippet;k=hexb(query.encode())
        queries[k]=query;docs=[]
        for i,title in candidates:
            ticket=hexb(title.encode());titles[ticket]=title;docs.append((i,ticket))
        rows[q]=[k,docs]
    threshold=get(D/"threshold-seal.json");old=get(D/"lex-orders.json.gz");assert sha(SERVER)==get(D/"registration.json")["runtime"]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
    host="http://127.0.0.1:"+str(port);sess=requests.Session();sess.trust_env=False
    args=[str(SERVER),"-m",str(ENCODER),"-ngl","99","-fit","off","--embeddings","--pooling","last","-c","4096","-b","2048","-ub","2048","-np","4","-t","3","-tb","3","--host","127.0.0.1","--port",str(port),"--no-warmup","-lv","3"]
    fallback_log=P/"embedding.log";cost={};vectors={};proof={}
    t0=time.perf_counter()
    with fallback_log.open("wb") as f:
        proc=subprocess.Popen(args,stdout=f,stderr=f,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(150):
                if proc.poll() is not None:raise RuntimeError("embedding process exited")
                try:
                    if sess.get(host+"/health",timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(.25)
            else:raise RuntimeError("embedding server unavailable")
            cost["startup_seconds"]=time.perf_counter()-t0
            for name,texts in [("titles",titles),("queries",queries)]:
                start=time.perf_counter();tokens={};limits=0
                for k,t in sorted(texts.items()):
                    res=sess.post(host+"/tokenize",json=dict(content=t,parse_special=False,add_special=False),timeout=20)
                    res.raise_for_status();ts=res.json()["tokens"];tokens[k]=ts[:511]+[END];limits+=len(ts)>511
                split=time.perf_counter();keys=sorted(tokens,key=lambda k:(len(tokens[k]),k))
                for off in range(0,len(keys),4):
                    subset=keys[off:off+4];res=sess.post(host+"/v1/embeddings",json=dict(input=[tokens[k] for k in subset],encoding_format="base64"),timeout=120)
                    res.raise_for_status();data=sorted(res.json()["data"],key=lambda x:x["index"]);assert len(data)==len(subset)
                    for k,v in zip(subset,data,strict=True):
                        emb=v["embedding"]
                        a=np.frombuffer(base64.b64decode(emb),dtype="<f4") if isinstance(emb,str) else np.array(emb,dtype="<f4")
                        assert a.shape==(4096,) and np.isfinite(a).all() and np.linalg.norm(a)>0
                        vectors[k]=a/np.linalg.norm(a)
                cost[name]=dict(unique=len(keys),tokens=sum(map(len,tokens.values())),clipped=limits,
                    tokenize_seconds=split-start,embedding_seconds=time.perf_counter()-split,
                    logical=sum(len(v[1]) for v in rows.values()) if name=="titles" else len(rows))
                print(name,cost[name],flush=True)
            own=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,process_name","--format=csv,noheader"],text=True)
            assert any(x.startswith(str(proc.pid)+",") and x.endswith("llama-server.exe") for x in own.splitlines())
            cost["device"]=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.used","--format=csv,noheader"],text=True).strip()
        finally:
            proc.terminate();proc.wait(timeout=25);sess.close()
    cost["process_seconds"]=time.perf_counter()-t0
    t1=time.perf_counter();result={}
    audit=set(sorted(rows,key=lambda q:hexb(("r50-vector-audit|"+q).encode()))[:8]);samples={}
    for q,(query,docs) in rows.items():
        u=vectors[query];values={i:float(np.dot(u,vectors[k])) for i,k in docs}
        rank=sorted(values,key=lambda i:-values[i]);marks=set(map(int,old[q]["edges"]))
        result[q]=dict(order=rank,scores=values,dense=rank[0],linked_dense=next((j for j in rank if j in marks),rank[0]),
               edges=sorted(marks),seed=old[q]["seed"],lex=old[q]["lex"],true=old[q]["true"],lex_order=old[q]["order"])
        row=result[q];a=row["dense"];b=row["linked_dense"]
        gap=None if a==b else values[a]-values[b]
        assert gap is None or gap>=0
        row["gap"]=gap
        row["adaptive"]=b if gap is not None and threshold["primary"] is not None and gap<=threshold["primary"] else a
        row["quarter"]=b if gap is not None and gap<=threshold["quarter"] else a
        if q in audit:
            samples[q]=[query,docs]
            for key in [query]+[k for _,k in docs]:
                proof[key]=base64.b64encode(vectors[key].astype("<f4").tobytes()).decode("ascii")
    cost["rank_seconds"]=time.perf_counter()-t1;cost["log"]=sha(fallback_log)
    put(D/"vector-check.json.gz",dict(rows=samples,vectors=proof));put(D/"orders.json.gz",result);put(D/"embedding-cost.json",cost)
    put(D/"retrieval-seal.json",dict(orders=sha(D/"orders.json.gz"),costs=sha(D/"embedding-cost.json"),test=sha(D/"vector-check.json.gz"),
            projected=sha(D/"projection-seal.json"),threshold=sha(D/"threshold-seal.json"),registration=sha(D/"registration.json"),encoder=DIGEST,code=sha(Path(__file__))))
    print("Ranks sealed",len(rows),cost["process_seconds"],flush=True)
if __name__=="__main__":main()
