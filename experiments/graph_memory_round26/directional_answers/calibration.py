"""Benchmark-native passage QA. Skip the memory interface and score only after the answer receipt is written."""
import os,time
import infer
from infer import ort,Tokenizer,WEIGHTS,ENCT
from prepare import D,P,RAW,read,save,sha,h,Path
def official_paragraph(text,parts):
    assert parts==[[0,len(text),0]]
    return text,[[0,len(text),0,len(text)]]
def main():
    assert (D/"forecast-seal.json").exists();keys=set(read(D/"predictions.json.gz"));view={}
    for art in read(RAW)["data"]:
        t=art["title"]
        for j,para in enumerate(art["paragraphs"]):
            for qa in para["qas"]:
                q=qa["id"]
                if q in keys:view[q]=[t,j,qa["question"],para["context"]]
    assert set(view)==keys and len(view)==576
    save(P/"native-passage-view.json.gz",view);view=read(P/"native-passage-view.json.gz")
    path=D/"calibration-predictions.json.gz";tok=Tokenizer.from_file(str(ENCT))
    o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1;o.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    o.add_session_config_entry("session.intra_op.allow_spinning","0")
    engine=ort.InferenceSession(str(WEIGHTS),sess_options=o,providers=["CPUExecutionProvider"])
    out={};begin=time.monotonic();old=infer.wire;infer.wire=official_paragraph
    try:
        for q,(_,_,query,body) in view.items():
            out[q]=infer.read_arm(query,body,[[0,len(body),0]],engine,tok,{})
    finally:infer.wire=old
    save(path,out);save(D/"calibration-seal.json",dict(forecasts=sha(path),plan=sha(D/"CALIBRATION_RU.md"),source=sha(Path(__file__)),
         reader=sha(D/"infer.py"),view=sha(P/"native-passage-view.json.gz"),primary=sha(D/"forecast-seal.json"),n=len(out),seconds=time.monotonic()-begin))
    import score
    off=score.scorer();payload=[];predicted={};ind={}
    for art in read(RAW)["data"]:
        ps=[]
        for para in art["paragraphs"]:
            keep=[]
            for qa in para["qas"]:
                q=qa["id"]
                if q not in out:continue
                z=out[q];text=para["context"][z["start"]:z["end"]]
                assert h(text)==z["answer_sha"];predicted[q]=text;answers=[a["text"] for a in qa["answers"]]
                ind[q]=dict(f1=off.metric_max_over_ground_truths(off.f1_score,text,answers),em=int(off.metric_max_over_ground_truths(off.exact_match_score,text,answers)))
                keep.append(qa)
            if keep:ps.append({"qas":keep})
        if ps:payload.append({"paragraphs":ps})
    save(D/"calibration-per-query.json.gz",ind)
    metrics=off.evaluate(payload,predicted)
    save(D/"calibration-results.json",dict(metrics=metrics,per_query=sha(D/"calibration-per-query.json.gz"),seal=sha(D/"calibration-seal.json"),
         n=len(ind),articles=len(payload),total_logical_tokens=sum(z["logical_tokens"] for z in out.values()),total_windows=sum(z["windows"] for z in out.values())))
    print(metrics)
if __name__=="__main__":main()
