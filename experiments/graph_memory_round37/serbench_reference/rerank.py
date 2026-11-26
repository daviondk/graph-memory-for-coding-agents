"""Frozen public MiniLM on CPU, 32 BGE candidates per state, no labels."""
from common import D, UP, R34, PUB, data, get, rows, save, sha
import os,sys,time
sys.path.insert(0,str(D/"runtime/pylib"))
os.environ["TOKENIZERS_PARALLELISM"]="false"
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

def main():
    pack=D/"runtime"; meta=get(D/"availability.json")
    model=pack/"model_quint8_avx2.onnx"
    assert sha(model)==meta["models"]["onnx/model_quint8_avx2.onnx"]
    assert sha(pack/"tokenizer.json")==meta["models"]["tokenizer.json"]
    tk=Tokenizer.from_file(str(pack/"tokenizer.json"));tk.enable_truncation(max_length=256,strategy="longest_first");tk.no_padding()
    op=ort.SessionOptions();op.intra_op_num_threads=5;op.inter_op_num_threads=1
    session=ort.InferenceSession(str(model),sess_options=op,providers=["CPUExecutionProvider"])
    feats=data(); batches=[]
    for r in rows(PUB/"items.jsonl.gz"):
        sid=r["state_id"]; fr=feats.get(sid)
        if fr is None or fr["split"]!="test":continue
        query="\n".join(r.get(k) or "" for k in ("information_need","current_subgoal","issue"))
        pool={c["evidence_id"]:c for c in r["candidate_evidence"]}; assert set(pool)==set(fr["ids"])
        for rank,idx in enumerate(np.argsort(fr["ranks"]["dense_state"])[:32]):
            doc=pool[fr["ids"][idx]]
            snippet=(doc.get("source_path") or "")+"\n"+(doc.get("content_excerpt") or "")
            enc=tk.encode(query,snippet)
            batches.append((len(enc.ids),sid,rank,int(idx),enc.ids,enc.type_ids))
    batches.sort(key=lambda v:v[:3])
    output={}
    start=time.perf_counter()
    for pos in range(0,len(batches),16):
        group=batches[pos:pos+16];length=max(p[0] for p in group)
        ids=np.zeros((len(group),length),dtype=np.int64); types=np.zeros_like(ids); masks=np.zeros_like(ids)
        for j,(n,_,_,_,tok,seg) in enumerate(group):
            ids[j,:n]=tok; types[j,:n]=seg; masks[j,:n]=1
        vals=session.run(None,dict(input_ids=ids,attention_mask=masks,token_type_ids=types))[0].reshape(-1)
        for item,score in zip(group,vals):
            _,sid,rank,idx,*_=item;output.setdefault(sid,[]).append([rank,idx,float(score)])
        if pos%1024==0:print(pos,len(batches),round(time.perf_counter()-start,1),flush=True)
    assert len(output)==214
    for scores in output.values():scores.sort()
    save(D/"reranker-scores.json.gz",output)
    print("done",len(batches),round(time.perf_counter()-start,1),flush=True)
if __name__=="__main__":main()
