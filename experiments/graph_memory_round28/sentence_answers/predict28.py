"""Use the frozen R26 decoder; only whole, layout-identical previous contexts may donate a prediction."""
from collections import Counter
import datetime,json,sys,time
from contexts28 import D,P,R26,ARMS,read,save,sha,h,ENCT,WEIGHTS,wire,Tokenizer,Path
import infer as old
import numpy as np
def atomic(path,x):
    for sec in (.01,.03,.1,.3,1.,2.):
        try:return save(path,x)
        except PermissionError:time.sleep(sec)
    return save(path,x)
def window_keys(tok,question,wiretext):
    q=list(tok.encode(question,add_special_tokens=False).ids);ctx=tok.encode(wiretext,add_special_tokens=False).ids
    prefix=[tok.token_to_id("[CLS]"),*q,tok.token_to_id("[SEP]")];sep=tok.token_to_id("[SEP]");width=384-len(prefix)-1;keys=[]
    for k in range(0,len(ctx),width-128):
        stop=min(k+width,len(ctx));ids=prefix+ctx[k:stop]+[sep]
        keys.append(h(np.asarray(ids,dtype="<i8").tobytes()))
        if stop==len(ctx):break
    return keys
def main():
    inputs=read(D/"context-seal.json");plan=read(D/"input-plan.json");assert inputs["plan"]==sha(D/"input-plan.json")
    assert inputs["contexts"]==sha(D/"contexts.json.gz")
    old_seal=read(R26/"forecast-seal.json")
    assert old_seal["forecasts"]==sha(R26/"predictions.json.gz") and sha(R26/"forecast-seal.json")==plan["old_forecast"]
    assert sha(R26/"infer.py")==old_seal["config"]["source"]==plan["reader_sha"] and sha(WEIGHTS)==plan["model"] and old.ort.__version__==old_seal["config"]["runtime"]
    assert sha(R26/"contexts.json.gz")==read(R26/"input-lock.json")["contexts"]
    cfg=dict(input_seal=sha(D/"context-seal.json"),source=sha(Path(__file__)),old_configuration=old_seal["config"],old_seal=sha(R26/"forecast-seal.json"))
    root=P/("predictions-"+h(json.dumps(cfg,sort_keys=True)));root.mkdir(exist_ok=True)
    o=old.ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1;o.execution_mode=old.ort.ExecutionMode.ORT_SEQUENTIAL
    o.add_session_config_entry("session.intra_op.allow_spinning","0")
    engine=old.ort.InferenceSession(str(WEIGHTS),sess_options=o,providers=["CPUExecutionProvider"])
    tok=Tokenizer.from_file(str(ENCT));view=read(Path("D:/CodexResearch/x20-r26-squad-qa/blind-input.json.gz"))
    prior=read(R26/"contexts.json.gz");old_preds=read(R26/"predictions.json.gz");rows=read(D/"contexts.json.gz");out={};used=Counter();t0=time.monotonic()
    def state(k):
        atomic(D/"progress.json",dict(state=k,done=len(out),total=len(rows),counts=used,elapsed_current_process=round(time.monotonic()-t0,2),
               updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    state("running")
    for q in sorted(rows,key=lambda q:h("r28-reader/"+q)):
        target=root/(q+".json");row=rows[q];title,question=view["qs"][q];text=view["docs"][title]
        if target.exists():result=read(target)
        else:
            cache={};rr={};counts=Counter();window_proof={}
            for arm in ARMS:
                a=row["arms"][arm];parts=row["base"]+a["extra"];w,layout=wire(text,parts);assert h(w)==a["wire_sha"]
                keys=window_keys(tok,question,w);canonical=h(json.dumps(keys));counts["logical_windows"]+=len(keys)
                matching=None
                for oldname,oldarm in prior[q]["arms"].items():
                    if oldarm["wire_sha"]!=a["wire_sha"]:continue
                    oparts=prior[q]["base"]+oldarm["extra"];ow,ol=wire(text,oparts)
                    if oparts!=parts or ol!=layout or ow!=w:continue
                    ok=window_keys(tok,question,ow);assert ok==keys
                    candidate=old_preds[q]["arms"][oldname]
                    assert candidate["receipt"]==h(w) and candidate["windows"]==len(keys) and h(text[candidate["start"]:candidate["end"]])==candidate["answer_sha"]
                    matching=oldname;prediction=candidate;break
                if matching is None:
                    before=len(cache);prediction=old.read_arm(question,text,parts,engine,tok,cache)
                    counts["new_onnx_windows"]+=len(cache)-before
                    counts["reused_within_question_windows"]+=len(keys)-(len(cache)-before)
                    counts["new_contexts"]+=1
                else:
                    counts["r26_reused_windows"]+=len(keys);counts["r26_reused_contexts"]+=1
                assert prediction["receipt"]==h(w) and prediction["windows"]==len(keys)
                window_proof[arm]=dict(key_digest=canonical,keys=keys,old_arm=matching,layout_digest=h(json.dumps(layout)))
                rr[arm]=prediction
            assert rr[ARMS[0]]["logical_tokens"]==rr[ARMS[1]]["logical_tokens"]
            result=dict(outputs=rr,checks=window_proof,counts=dict(counts))
            atomic(target,result)
        out[q]=result;used.update(result["counts"]);state("running")
        if len(out)%48==0:print(len(out),dict(used),round(time.monotonic()-t0,2),flush=True)
    assert used["logical_windows"]==used["new_onnx_windows"]+used["reused_within_question_windows"]+used["r26_reused_windows"]
    atomic(D/"predictions.json.gz",out);atomic(D/"forecast-seal.json",dict(cfg=cfg,forecasts=sha(D/"predictions.json.gz"),counts=used,questions=len(out)))
    state("sealed")
if __name__=="__main__":main()
