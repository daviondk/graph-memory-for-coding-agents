"""Run real ONNX admissions with optional reuse of compact window winners."""
from collections import defaultdict
import hashlib
from pathlib import Path
import random
from time import perf_counter_ns as now
import numpy as np
from trigger import HERE,PREVIOUS,P,CHOICES,routing,hashkey,read,save,sha
from capture import mappings,Tokenizer,ENCT,WEIGHTS,ort

def best(a,b,seg):
    score=np.full((len(seg),30),-np.inf,dtype=np.float32)
    for d in range(min(30,len(seg))):
        n=len(seg)-d;valid=(seg[:n]>=0)&(seg[:n]==seg[d:])
        score[:n,d]=np.where(valid,a[:n]+b[d:],-np.inf)
    i,d=map(int,np.unravel_index(np.argmax(score),score.shape))
    return (i,d,float(score[i,d])) if np.isfinite(score[i,d]) else None

def answer(tok,session,query,source,parts,cache):
    winner=None;calls=tokens=windows=0
    for ids,p,seg,lo,hi,layout in mappings(tok,query,source,parts):
        windows+=1
        key=(ids.astype("<i8").tobytes(),layout.tobytes()) if cache is not None else None
        if cache is not None and key in cache:r=cache[key]
        else:
            a,b=session.run(["start_logits","end_logits"],{"input_ids":ids[None,:],"attention_mask":np.ones((1,len(ids)),dtype=np.int64)})
            r=best(a[0,p:p+len(seg)],b[0,p:p+len(seg)],seg);calls+=1;tokens+=len(ids)
            if cache is not None:cache[key]=r
        if r and (winner is None or r[2]>winner["score"]):
            i,d,score=r;winner={"score":score,"start":int(lo[i]),"end":int(hi[i+d]),"body_index":int(seg[i]),"answer_tokens":d+1}
    if winner:winner["windows"]=windows
    return winner,calls,tokens

def main():
    obs=read(HERE/"observations.json.gz");routes=read(HERE/"routes.json.gz");learn=read(HERE/"route-seal.json")
    x=np.array([obs[q]["x"] for q in sorted(obs) if obs[q]["training"]]);mu=x.mean(axis=0);std=x.std(axis=0);std[std<1e-8]=1
    by=defaultdict(list)
    for q,r in routes.items():by[r["title"]].append(q)
    panel=sorted(min(qs,key=lambda q:hashkey("trigger-service-v1",q)) for qs in by.values())
    assert len(panel)==24
    c=read(PREVIOUS/"contexts.json.gz");prior=read(PREVIOUS/"predictions.json.gz");choice=read(CHOICES)
    src=read(P/"blind-input.json.gz");tok=Tokenizer.from_file(str(ENCT))
    settings=ort.SessionOptions();settings.intra_op_num_threads=2;settings.inter_op_num_threads=1
    settings.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;settings.add_session_config_entry("session.intra_op.allow_spinning","0")
    engine=ort.InferenceSession(str(WEIGHTS),sess_options=settings,providers=["CPUExecutionProvider"])
    modes=["direct","base","gain_fresh","gain_cached","score_cached"]
    lock={"policy":sha(HERE/"route-seal.json"),"protocol":sha(HERE/"SERVICE_RU.md"),"script":sha(Path(__file__)),"panel":panel,"modes":modes}
    seal=HERE/"service-plan.json"
    if seal.exists():assert read(seal)==lock
    else:save(seal,lock)
    logs=[]
    for rep in range(2):
        order=list(panel);random.Random(rep+28614).shuffle(order)
        for q in order:
            title,query=src["qs"][q];text=src["docs"][title];base=c[q]["base"];extra=c[q]["arms"]["both"]["extra"]
            tmp=modes.copy();random.Random(hashkey("trigger-scheduling-v1",str(rep)+q)).shuffle(tmp)
            for mode in tmp:
                cache={} if mode.endswith("_cached") else None
                start=now();admit=mode=="direct"
                pred,n,t=answer(tok,engine,query,text,base+extra if admit else base,cache)
                if mode not in ("direct","base"):
                    features=routing(pred,base,choice[q]["cut"])
                    if mode.startswith("gain"):
                        m="gain";intercept,beta=learn["coef"][m]
                        value=intercept+(np.array(features)-mu)/std@np.array(beta)
                    else:m="low_score";value=-features[0]
                    admit=value>=learn["threshold"][m]
                    assert admit==bool(routes[q]["online"][m])
                    if admit:
                        pred,n2,t2=answer(tok,engine,query,text,base+extra,cache);n+=n2;t+=t2
                elapsed=now()-start;target=prior[q]["arms"]["both" if admit else "base"]
                assert all(pred[k]==target[k] for k in ("score","start","end","answer_tokens"))
                logs.append([rep,q,title,mode,int(admit),n,t,elapsed,pred["start"],pred["end"]])
            if len(logs)%30==0:print(len(logs),flush=True)
    save(HERE/"service-times.json.gz",logs);save(HERE/"service-receipt.json",{"rows":len(logs),
          "actual_forwards":sum(r[5] for r in logs),"times":sha(HERE/"service-times.json.gz"),"plan":sha(seal)})
if __name__=="__main__":main()

