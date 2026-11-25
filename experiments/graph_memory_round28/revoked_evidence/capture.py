"""Capture independent full ONNX forwards before and after literal evidence changes."""
from collections import defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from time import perf_counter_ns as now

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parents[1]/"graph_memory_round26/directional_answers"
sys.path.insert(0,str(PREVIOUS))
from prepare import P,WEIGHTS,ENCT,wire,enc,read,save,sha,h,Tokenizer
sys.path.append("D:/CodexResearch/x20-r23-multidoc2dial/libs")
import onnxruntime as ort
import numpy as np

PRIVATE=Path("D:/CodexResearch/x20-r28-revoked-spans")
def key(value):
    return hashlib.sha256(("revoke-question-v1/"+value).encode()).digest()

def remove(parts, left, right):
    result=[]
    for l,r,anchor in parts:
        if l>=right or r<=left:
            result.append([l,r,anchor]);continue
        if l<left:result.append([l,left,anchor])
        if right<r:result.append([right,r,right])
    assert all(r<=left or l>=right for l,r,_ in result)
    return result

def mappings(tokenizer,query,source,parts):
    text,spans=wire(source,parts)
    item=enc(tokenizer,text)
    prefix=[tokenizer.token_to_id("[CLS]"),*enc(tokenizer,query).ids,tokenizer.token_to_id("[SEP]")]
    width=384-len(prefix)-1
    owners=[];lows=[];highs=[];j=0
    for l,r in item.offsets:
        while j<len(spans) and l>=spans[j][1]: j+=1
        if j<len(spans) and spans[j][0]<=l<r<=spans[j][1]:
            a,_,origin,_=spans[j]
            owners.append(j);lows.append(origin+l-a);highs.append(origin+r-a)
        else:
            owners.append(-1);lows.append(-1);highs.append(-1)
    for k in range(0,len(owners),width-128):
        end=min(k+width,len(owners))
        ids=np.array([*prefix,*item.ids[k:end],tokenizer.token_to_id("[SEP]")],dtype=np.int64)
        labels=np.array(owners[k:end],dtype=np.int32)
        # Segment numbering is relative to each window. Equal labels allow a span
        # within a single source occurrence. Headers have no source owner.
        renumber={};canon=np.array([-1 if x<0 else renumber.setdefault(int(x),len(renumber)) for x in labels],dtype="<i2")
        yield ids,len(prefix),labels,np.array(lows[k:end],dtype=np.int32),np.array(highs[k:end],dtype=np.int32),canon
        if end==len(owners): break

def main():
    prior=read(PREVIOUS/"predictions.json.gz")
    contexts=read(PREVIOUS/"contexts.json.gz")
    blind=read(P/"blind-input.json.gz");by=defaultdict(list)
    for q,(title,_) in blind["qs"].items():by[title].append(q)
    cohort=sorted(q for qs in by.values() for q in sorted(qs,key=key)[:2])
    assert len(cohort)==96 and len(by)==48
    plan={"questions":cohort,"script":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md"),
          "parent":sha(PREVIOUS/"forecast-seal.json"),"input":sha(P/"blind-input.json.gz"),
          "model":sha(WEIGHTS),"tokenizer":sha(ENCT),"ort":ort.__version__}
    planfile=HERE/"capture-plan.json"
    if planfile.exists():assert read(planfile)==plan
    else:save(planfile,plan)
    root=PRIVATE/sha(planfile);root.mkdir(parents=True,exist_ok=True)
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    opts.add_session_config_entry("session.intra_op.allow_spinning","0")
    session=ort.InferenceSession(str(WEIGHTS),sess_options=opts,providers=["CPUExecutionProvider"])
    tok=Tokenizer.from_file(str(ENCT));all_descriptions={}
    for i,q in enumerate(cohort):
        forecast=root/(q+".json");data=root/(q+".npz")
        if not forecast.exists():
            title,query=blind["qs"][q];source=blind["docs"][title];old=contexts[q]["base"]
            chosen=prior[q]["arms"]["base"];record=old[chosen["body_index"]]
            changed=remove(old,record[0],record[1])
            modes={"base":old,"append":old+contexts[q]["arms"]["both"]["extra"],"retract":changed}
            arrays={};paths={}
            for mode,parts in modes.items():
                windows=[]
                for n,(ids,p,seg,l,r,canon) in enumerate(mappings(tok,query,source,parts)):
                    start=now()
                    logits=session.run(["start_logits","end_logits"],{"input_ids":ids[None,:],"attention_mask":np.ones((1,len(ids)),dtype=np.int64)})
                    elapsed=now()-start
                    name=f"{mode}_{n}_";length=len(seg)
                    for label,arr in (("a",logits[0][0,p:p+length]),("b",logits[1][0,p:p+length]),("seg",seg),("lo",l),("hi",r)):
                        arrays[name+label]=arr
                    model_key=hashlib.sha256(ids.astype("<i8").tobytes()).hexdigest()
                    mask_key=hashlib.sha256(canon.tobytes()).hexdigest()
                    windows.append([model_key,mask_key,len(ids),elapsed])
                paths[mode]={"windows":windows,"parts":parts,"wire":h(wire(source,parts)[0])}
            with data.open("wb") as dest:np.savez_compressed(dest,**arrays)
            save(forecast,{"title":title,"cut":record[:2],"old_answer":[chosen["start"],chosen["end"]],"states":paths,"arrays":sha(data)})
        info=read(forecast);assert info["arrays"]==sha(data)
        all_descriptions[q]=info
        if (i+1)%12==0:print("full forwards",i+1,flush=True)
    save(HERE/"state-forecasts.json.gz",all_descriptions)
    save(HERE/"forecast-seal.json",{"plan":sha(planfile),"forecasts":sha(HERE/"state-forecasts.json.gz"),"n":len(cohort)})
if __name__=="__main__":
    main()

