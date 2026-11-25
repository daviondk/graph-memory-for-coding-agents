"""Run the same source evidence through five grouping rules under three updates."""
from collections import defaultdict
import hashlib
from pathlib import Path
import sys
from time import perf_counter_ns as now
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"read_trigger"))
from serve import best
from capture import PREVIOUS,P,WEIGHTS,ENCT,PRIVATE,key,read,save,sha,remove,mappings,Tokenizer,ort,np

MODES=("stream","single","repack3","stable3","anchors")
def groups(records,kind,title,original):
    out=[]
    for pos,(parent,record) in enumerate(records):
        if kind=="stream":new=pos==0
        elif kind=="single":new=True
        elif kind=="repack3":new=pos%3==0
        elif kind=="stable3":new=pos==0 or parent//3!=records[pos-1][0]//3
        else:
            # Define a boundary once for an observed source occurrence. Surviving
            # pieces of a split occurrence use its old identity.
            anchor=original[parent] if parent<len(original) else record
            signature=hashlib.sha256((title+":"+str(anchor)).encode()).digest()
            new=pos==0 or parent!=records[pos-1][0] and int.from_bytes(signature[:8],"big")%3==0
        if new:out.append([])
        out[-1].append(record)
    return out

def run_parts(session,tok,query,text,parts,cache,fresh=False):
    maximum=None;windows=[];calls=0;elapsed=0
    for group in parts:
        for ids,p,seg,l,h,layout in mappings(tok,query,text,group):
            tag=hashlib.sha256(ids.astype("<i8").tobytes()).hexdigest()+hashlib.sha256(layout.tobytes()).hexdigest()
            if fresh or tag not in cache:
                start=now()
                a,b=session.run(["start_logits","end_logits"],{"input_ids":ids[None,:],"attention_mask":np.ones((1,len(ids)),dtype=np.int64)})
                r=best(a[0,p:p+len(seg)],b[0,p:p+len(seg)],seg);calls+=1;elapsed+=now()-start
                if tag in cache:assert cache[tag]==r
                cache[tag]=r
            else:r=cache[tag]
            windows.append([tag,len(ids)])
            if r and (maximum is None or r[2]>maximum[0]):
                i,d,score=r;maximum=[score,int(l[i]),int(h[i+d])]
    return {"answer":maximum,"windows":windows,"groups":len(parts)},calls,elapsed

def main():
    plan=read(HERE.parent/"revoked_evidence/capture-plan.json");cohort=plan["questions"]
    current=read(PREVIOUS/"contexts.json.gz");prev=read(PREVIOUS/"predictions.json.gz");blind=read(P/"blind-input.json.gz")
    audit_titles=sorted({current[q]["title"] for q in cohort},key=lambda x:key("group-audit/"+x))[:4]
    audit_questions={min((q for q in cohort if current[q]["title"]==t),key=key) for t in audit_titles}
    lock={"protocol":sha(HERE/"PROTOCOL_RU.md"),"script":sha(Path(__file__)),"cohort":cohort,"audit_questions":sorted(audit_questions),
          "upstream":sha(HERE.parent/"revoked_evidence/capture-plan.json"),"model":sha(WEIGHTS),"tokenizer":sha(ENCT),"local_decoder":sha(HERE.parent/"read_trigger/serve.py")}
    path=HERE/"plan.json"
    if path.exists():assert read(path)==lock
    else:save(path,lock)
    root=PRIVATE/("group-"+sha(path));root.mkdir(parents=True,exist_ok=True)
    settings=ort.SessionOptions();settings.intra_op_num_threads=2;settings.inter_op_num_threads=1
    settings.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;settings.add_session_config_entry("session.intra_op.allow_spinning","0")
    engine=ort.InferenceSession(str(WEIGHTS),sess_options=settings,providers=["CPUExecutionProvider"]);tok=Tokenizer.from_file(str(ENCT))
    receipts={}
    for ix,q in enumerate(cohort):
        dest=root/(q+".json")
        if not dest.exists():
            title,query=blind["qs"][q];text=blind["docs"][title];base=current[q]["base"];extra=current[q]["arms"]["both"]["extra"]
            full=list(enumerate(base));more=list(enumerate(base+extra))
            winner=base[prev[q]["arms"]["base"]["body_index"]][:2]
            j=min(range(len(base)),key=lambda n:key("group-retract/"+q+"/"+str(n)));random_cut=base[j][:2]
            states={"base":full,"append":more}
            for state,c in (("winner",winner),("random",random_cut)):
                states[state]=[(i,piece) for i,part in full for piece in remove([part],*c)]
            cache={};pred={};calls=total=independent=0
            for state,records in states.items():
                pred[state]={}
                for mode in MODES:
                    grouping=groups(records,mode,title,base+extra)
                    assert [x for g in grouping for x in g]==[x for i,x in records]
                    row,n,ns=run_parts(engine,tok,query,text,grouping,cache)
                    calls+=n;total+=ns;pred[state][mode]=row
                    if q in audit_questions and state=="random" and mode in ("stream","repack3","stable3","single","anchors"):
                        check,count,_=run_parts(engine,tok,query,text,grouping,cache,fresh=True);independent+=count
                        assert check==row
                if state=="base":assert pred[state]["repack3"]==pred[state]["stable3"]
                if state in ("base","append"):
                    outcome=prev[q]["arms"]["base" if state=="base" else "both"]
                    assert pred[state]["stream"]["answer"]==[outcome["score"],outcome["start"],outcome["end"]]
            save(dest,{"title":title,"read":pred,"unique_calls":calls,"fresh_audit_calls":independent,"model_ns":total,
                 "random_cut":random_cut,"winner_cut":winner,"random_is_winner":random_cut==winner})
        receipts[q]=read(dest)
        if (ix+1)%12==0:print(ix+1,flush=True)
    save(HERE/"forecasts.json.gz",receipts);save(HERE/"forecast-lock.json",{"forecasts":sha(HERE/"forecasts.json.gz"),"plan":sha(path),"n":len(receipts)})
if __name__=="__main__":main()

