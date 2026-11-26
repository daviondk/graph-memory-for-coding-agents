"""Seal the label-free delivered documents, then extract spans from each arm independently."""
import gzip, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
from tokenizers import Tokenizer
sys.path.append("D:/CodexResearch/x20-r23-multidoc2dial/libs")
import onnxruntime as ort

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
PRIVATE=Path("D:/CodexResearch/x20-r33-musique-answers")
SOURCE=Path("D:/CodexResearch/x20-r32-musique/musique.jsonl")
PRIOR=WORK/"graph_memory_round32/musique_links"
MODEL=WORK/"graph_memory_round3/qa/models/reader"
ARMS=("seed","title","mention_title","local_static")

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def put(p,data):
    b=(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
    stage=p.with_name(p.name+".tmp")
    stage.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
    os.replace(stage,p)
def prepare():
    assert sha(SOURCE)=="15fa63794d18a94ce12411aca6e2327e65b6e83b0b1490efab3f1962e48abf3b"
    assert sha(PRIOR/"predictions.json.gz")==get(PRIOR/"seal.json")["predictions"]
    policy=get(PRIOR/"predictions.json.gz")
    view={}
    with SOURCE.open(encoding="utf8") as src:
        for line in src:
            r=json.loads(line); key=r["id"]; a=policy[key]
            picks={"seed":[a["seed"]]}
            for mode in ARMS[1:]:picks[mode]=[a["seed"],a["next"][mode]]
            ids={i for sel in picks.values() for i in sel}
            docs={str(p["idx"]):[p["title"],p["paragraph_text"]] for p in r["paragraphs"] if p["idx"] in ids}
            assert len(docs)==len(ids) and key not in view
            view[key]=[r["question"],docs,picks]
    assert len(view)==len(policy)==2417
    put(PRIVATE/"view.json.gz",view)
    plan={k:sha(p) for k,p in {"source":SOURCE,"input_view":PRIVATE/"view.json.gz","policy":PRIOR/"predictions.json.gz","model":MODEL/"model_quantized.onnx","tokenizer":MODEL/"tokenizer.json","reader":Path(__file__),"protocol":HERE/"PROTOCOL_RU.md"}.items()}
    plan.update(runtime=ort.__version__,arms=ARMS,provider="CPUExecutionProvider",document_limit=144,question_limit=64,threads=2)
    put(HERE/"plan.json",plan)

def encode_doc(tok,fields):
    ids=[];segments=[]
    for field,s in enumerate(fields):
        if field and len(ids)<144:ids.append(tok.token_to_id("[SEP]"));segments.append(None)
        enc=tok.encode(s,add_special_tokens=False)
        room=144-len(ids); ids.extend(enc.ids[:room])
        segments.extend((field,a,b) for a,b in enc.offsets[:room])
    return ids,segments

def predict(q,docids,encoded,engine,tok):
    sep=tok.token_to_id("[SEP]")
    ids=[tok.token_to_id("[CLS]"),*q,sep];owners=[None]*len(ids)
    for k in docids:
        vals,spans=encoded[str(k)]
        ids.extend(vals); owners.extend(None if z is None else (k,*z) for z in spans)
        ids.append(sep);owners.append(None)
    arr=np.asarray([ids],dtype=np.int64)
    start,end=engine.run(["start_logits","end_logits"],{"input_ids":arr,"attention_mask":np.ones_like(arr)})
    n=len(ids);scores=np.full((n,30),-np.inf,dtype=np.float32)
    owner=np.asarray([-1 if v is None else v[0]*2+v[1] for v in owners])
    for d in range(min(n,30)):
        k=n-d;valid=(owner[:k]>=0)&(owner[:k]==owner[d:])
        scores[:k,d]=np.where(valid,start[0,:k]+end[0,d:],-np.inf)
    i,d=map(int,np.unravel_index(np.argmax(scores),scores.shape))
    assert np.isfinite(scores[i,d])
    doc,field,left,_=owners[i];right=owners[i+d][3]
    return [doc,field,left,right,n]

def main():
    plan=get(HERE/"plan.json")
    assert plan["reader"]==sha(Path(__file__)) and plan["input_view"]==sha(PRIVATE/"view.json.gz") and plan["model"]==sha(MODEL/"model_quantized.onnx") and plan["tokenizer"]==sha(MODEL/"tokenizer.json") and plan["runtime"]==ort.__version__
    view=get(PRIVATE/"view.json.gz"); tok=Tokenizer.from_file(str(MODEL/"tokenizer.json"))
    so=ort.SessionOptions();so.intra_op_num_threads=2;so.inter_op_num_threads=1
    so.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    session=ort.InferenceSession(str(MODEL/"model_quantized.onnx"),sess_options=so,providers=["CPUExecutionProvider"])
    key=sha(HERE/"plan.json"); saved=PRIVATE/("progress-"+key+".json.gz")
    out=get(saved) if saved.exists() else {};tic=time.perf_counter()
    for qid,(question,docs,arms) in view.items():
        if qid in out:continue
        q=tok.encode(question,add_special_tokens=False).ids[:64];encoded={k:encode_doc(tok,v) for k,v in docs.items()};cache={}
        for mode in ARMS:
            pick=tuple(arms[mode])
            if pick not in cache:cache[pick]=predict(q,pick,encoded,session,tok)
        out[qid]={m:cache[tuple(arms[m])] for m in ARMS}
        if len(out)%64==0:
            put(saved,out)
            print(len(out),round(time.perf_counter()-tic,1),flush=True)
    assert set(out)==set(view)
    put(saved,out);put(HERE/"predictions.json.gz",out)
    put(HERE/"seal.json",{"plan":key,"predictions":sha(HERE/"predictions.json.gz")})
if __name__=="__main__":
    {"prepare":prepare,"predict":main}[sys.argv[1]]()
