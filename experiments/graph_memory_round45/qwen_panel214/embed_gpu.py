"""Encode full supplied candidate pools using the identical GPU pipeline, with atomic per-state receipts."""
from common import *

RUNTIME=CACHE/"runs-r40-214-gpu-v1"


def main():
    if os.environ.get("R40_GPU_LEASE")!="1":
        raise RuntimeError("Acquire shared GPU lease with gpu.ps1.")
    panel=read(OUT/"panel.json")
    sequence=panel["order"]
    assert len(sequence)==214 and sha(OUT/"PROTOCOL_RU.md")==panel["protocol"] and sha(CACHE/NAME)==DIGEST
    saved=read(R39SRC/"gpu-qwen-reference.json")
    assert saved.keys()==set(panel["pilot"])
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as f:
        states={r["state_id"]:r for r in map(json.loads,f) if r["state_id"] in panel["repo"]}
    assert states.keys()==set(sequence)
    RUNTIME.mkdir(exist_ok=True)
    fingerprint={p:sha(OUT/p) for p in ("PROTOCOL_RU.md","panel.json","common.py","embed_gpu.py")}
    fingerprint.update(weights=DIGEST,exe=sha(EXE),preprocessing=sha(R39SRC/"reference.py"))
    listener=socket.socket();listener.bind(("127.0.0.1",0));port=listener.getsockname()[1];listener.close()
    cli=[str(EXE),"-m",str(CACHE/NAME),"-ngl","99","-fit","off","--embeddings","--pooling","last",
         "-c","4096","-b","2048","-ub","2048","-t","3","-tb","3","-np","4","--host","127.0.0.1",
         "--port",str(port),"--no-warmup","-lv","5"]
    logname="gpu-"+str(time.time_ns())+".log"
    log=(RUNTIME/logname).open("wb")
    proc=subprocess.Popen(cli,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES="0"))
    http=requests.Session();http.trust_env=False
    address="http://127.0.0.1:"+str(port)
    predictions={};receipt={};pilot_check={}
    try:
        for _ in range(90):
            if proc.poll() is not None:
                raise RuntimeError("GPU process exited during startup")
            try:
                if http.get(address+"/health",timeout=1).ok: break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("GPU process not ready")
        for q in sequence:
            cachepath=RUNTIME/(hashlib.sha256(q.encode()).hexdigest()+".json")
            if cachepath.exists():
                result=read(cachepath)
                assert result["input"]==fingerprint and result["state"]==q
                value=result["record"]
            else:
                value=process_state(http,address,states[q])
                tmp=cachepath.with_suffix(".tmp")
                tmp.write_text(json.dumps(dict(input=fingerprint,state=q,record=value),sort_keys=True),encoding="utf8")
                tmp.replace(cachepath)
            predictions[q]=value;receipt[q]=sha(cachepath)
            if q in saved:
                old=saved[q]
                assert old["lengths"]==value["lengths"] and old["scores"].keys()==value["scores"].keys()
                pilot_check[q]=dict(sameLists=old["ranks"]==value["ranks"],maxCosDifference=max(abs(v-old["scores"][k]) for k,v in value["scores"].items()))
            if len(predictions)%10==0 or len(predictions)==len(sequence):
                save("progress.json",dict(states=len(predictions),total=len(sequence),input=fingerprint,seconds=sum(r["seconds"] for r in predictions.values()),
                                          tokens=sum(r["tokens"] for r in predictions.values())))
                print("Completed",len(predictions),"of",len(sequence),flush=True)
    finally:
        proc.terminate();proc.wait(timeout=30);log.close()
    output=(RUNTIME/logname).read_text(encoding="utf8",errors="replace")
    import re
    evidence=[s.strip() for s in output.splitlines() if re.search(r"offloaded [1-9][0-9]*/[0-9]+ layers to GPU|using device CUDA0|CUDA0 model buffer size|CUDA0 \(NVIDIA",s,re.I)]
    assert evidence,"Missing hardware confirmation in verbose runtime log"
    save("qwen-scores.json.gz",predictions)
    save("gpu-seal.json",dict(forecasts=sha(OUT/"qwen-scores.json.gz"),receipts=receipt,inputs=fingerprint,
                              log=sha(RUNTIME/logname),backend=evidence,matched_pilot=pilot_check,canonical_weights=DIGEST))
    print("sealed 214 Qwen forecasts")


if __name__=="__main__":
    main()
