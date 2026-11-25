"""Build a CPU-only E5 index of the common candidate pool; no annotations enter this file."""
from common import *
import numpy as np
import onnxruntime as ort
import time

def texts(view):
    out=["query: "+r[2] for r in view["q"]]
    for u in view["blocks"]:
        _,title,body=view["documents"][u["doc"]]
        out.append("passage: "+title+" "+body[u["a"]:u["b"]])
    return out

def main():
    session_opts=ort.SessionOptions()
    session_opts.intra_op_num_threads=2
    session_opts.inter_op_num_threads=1
    session_opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    session_opts.add_session_config_entry("session.intra_op.allow_spinning","0")
    session=ort.InferenceSession(str(MODEL/"model_qint8_avx512_vnni.onnx"),sess_options=session_opts,providers=["CPUExecutionProvider"])
    t=tok()
    v=get_views()
    items=texts(v)
    lock=read(ROOT/"input-lock.json")
    assert all(checksum(MODEL/f)==s for f,s in lock["model_files"].items())
    codes=[t.encode(s,add_special_tokens=False).ids[:510] for s in items]
    need=sorted(range(len(items)),key=lambda i:(len(codes[i]),i))
    vectors=np.empty((len(items),384),dtype="float32")
    begin=time.monotonic()
    for j in range(0,len(need),24):
        group=need[j:j+24]
        length=len(codes[group[-1]])+2
        inp=np.zeros((len(group),length),dtype=np.int64)
        mask=np.zeros_like(inp)
        for k,i in enumerate(group):
            doc=[t.token_to_id("[CLS]"),*codes[i],t.token_to_id("[SEP]")]
            inp[k,:len(doc)]=doc
            mask[k,:len(doc)]=1
        x=session.run(None,{"input_ids":inp,"token_type_ids":np.zeros_like(inp),"attention_mask":mask})[0]
        emb=(x*mask[:,:,None].astype(np.float32)).sum(axis=1)/mask.sum(axis=1,keepdims=True)
        vectors[group]=(emb/np.linalg.norm(emb,axis=1,keepdims=True)).astype(np.float32)
        if j%960==0:print(j,len(need),round(time.monotonic()-begin,1),flush=True)
    assert np.isfinite(vectors).all() and np.max(np.abs(np.linalg.norm(vectors,axis=1)-1))<1e-5
    path=CACHE/"e5.npy"
    np.save(path,vectors,allow_pickle=False)
    save(ROOT/"encoder-receipt.json",dict(weights=lock["model_files"],view=lock["view"],vectors=checksum(path),shape=list(vectors.shape),
         execution="CPUExecutionProvider",onnxruntime=ort.__version__,numpy=np.__version__,threads=2,seconds=time.monotonic()-begin,
         code=checksum(Path(__file__))))
    print("sealed",len(vectors),flush=True)

if __name__=="__main__":
    main()
