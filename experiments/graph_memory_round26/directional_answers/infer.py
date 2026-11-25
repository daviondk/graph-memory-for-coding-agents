"""Extract a single continuous answer from delivered source spans with the sealed DistilBERT checkpoint."""
import datetime,os,sys,time
from prepare import D,P,ARMS,MODEL,WEIGHTS,ENCT,enc,wire,sha,h,read,save,Tokenizer,Path
sys.path.append("D:/CodexResearch/x20-r23-multidoc2dial/libs")
import numpy as np
import onnxruntime as ort
def read_arm(query,text,parts,session,tok,cache):
    content,segments=wire(text,parts);body=enc(tok,content);q=enc(tok,query).ids
    qprefix=[tok.token_to_id("[CLS]"),*q,tok.token_to_id("[SEP]")];tail=tok.token_to_id("[SEP]")
    width=384-len(qprefix)-1;assert width>128
    starts=np.asarray([z[0] for z in segments]);ends=np.asarray([z[1] for z in segments])
    off=np.asarray(body.offsets);seg=np.full(len(off),-1,dtype=int)
    if len(starts):
        owners=np.searchsorted(starts,off[:,0],side="right")-1
        valid=(owners>=0)&(off[:,1]<=ends[np.maximum(0,owners)])
        seg[valid]=owners[valid]
    k=0;winner=None;windows=logical=0
    while k<len(body.ids):
        stop=min(k+width,len(body.ids));input_ids=tuple(qprefix+body.ids[k:stop]+[tail]);n=stop-k
        if input_ids not in cache:
            x=np.asarray([input_ids],dtype=np.int64)
            output=session.run(["start_logits","end_logits"],{"input_ids":x,"attention_mask":np.ones_like(x)})
            cache[input_ids]=(output[0][0].copy(),output[1][0].copy())
        x0,x1=cache[input_ids];windows+=1;logical+=len(input_ids)
        a=x0[len(qprefix):len(qprefix)+n];b=x1[len(qprefix):len(qprefix)+n]
        s=seg[k:stop];scores=np.full((n,30),-np.inf,dtype=np.float32)
        for shift in range(min(30,n)):
            count=n-shift;ok=(s[:count]>=0)&(s[:count]==s[shift:])
            scores[:count,shift]=np.where(ok,a[:count]+b[shift:],-np.inf)
        i,dist=map(int,np.unravel_index(np.argmax(scores),scores.shape));score=float(scores[i,dist])
        if np.isfinite(score) and (winner is None or score>winner[0]):
            sid=int(s[i]);pstart,pend,source_start,source_end=segments[sid]
            l=source_start+int(off[k+i,0])-pstart;r=source_start+int(off[k+i+dist,1])-pstart
            assert source_start<=l<r<=source_end and text[l:r]==content[off[k+i,0]:off[k+i+dist,1]]
            winner=(score,l,r,sid,k,i,dist+1)
        if stop>=len(body.ids):break
        k+=width-128
    assert winner is not None
    score,l,r,sid,k,i,n=winner
    return dict(start=l,end=r,body_index=sid,score=score,window_start_token=k,answer_tokens=n,
                windows=windows,logical_tokens=logical,receipt=h(content),answer_sha=h(text[l:r]))
def main():
    lock=read(D/"input-lock.json");assert lock["model"]==sha(WEIGHTS) and lock["view"]==sha(P/"blind-input.json.gz")
    assert lock["contexts"]==sha(D/"contexts.json.gz") and lock["cased_tokenizer"]==sha(ENCT)
    cfg=dict(inputs=sha(D/"input-lock.json"),source=sha(Path(__file__)),runtime=ort.__version__,provider="CPUExecutionProvider",
             intra_threads=2,inter_threads=1,window=384,overlap=128,max_answer_tokens=30,batching=1)
    root=P/("cache-"+h(str(sorted(cfg.items()))));root.mkdir(exist_ok=True)
    o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1;o.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    o.add_session_config_entry("session.intra_op.allow_spinning","0")
    engine=ort.InferenceSession(str(WEIGHTS),sess_options=o,providers=["CPUExecutionProvider"])
    tok=Tokenizer.from_file(str(ENCT));allrows=read(D/"contexts.json.gz");view=read(P/"blind-input.json.gz")
    out={};physical=0;logical=0;failures=0;start=time.monotonic()
    def status(state):
        save(D/"progress.json",dict(state=state,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),questions_done=len(out),
             questions_total=len(allrows),unique_evaluations=physical,logical_windows=logical,wall_seconds=round(time.monotonic()-start,3),failures=failures))
    status("running")
    for q in sorted(allrows,key=lambda i:h("r26-eval/"+i)):
        p=root/(q+".json");cache={};row=allrows[q];title,query=view["qs"][q]
        if p.exists():r=read(p)
        else:
            t=time.monotonic();a={};src=view["docs"][title]
            for arm in ARMS:
                config=row["arms"][arm];parts=row["base"]+config["extra"]
                a[arm]=read_arm(query,src,parts,engine,tok,cache)
                assert a[arm]["receipt"]==config["wire_sha"]
            assert len({a[k]["logical_tokens"] for k in ARMS[1:]})==1
            r=dict(arms=a,physical_windows=len(cache),logical_windows=sum(z["windows"] for z in a.values()),
                 seconds=round(time.monotonic()-t,4))
            save(p,r)
        out[q]=r;physical+=r["physical_windows"];logical+=r["logical_windows"];status("running")
        if len(out)%48==0:print(len(out),physical,round(time.monotonic()-start,2),flush=True)
    save(D/"predictions.json.gz",out)
    save(D/"forecast-seal.json",dict(config=cfg,forecasts=sha(D/"predictions.json.gz"),n=len(out),physical=physical,logical=logical))
    status("sealed")
if __name__=="__main__":main()
