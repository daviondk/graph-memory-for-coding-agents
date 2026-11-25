"""Capture released-baseline-to-local-reader transfer, blind to test answers."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent
NATIVE=HERE.parent/"native_revisions"
sys.path.insert(0,str(NATIVE))
from fetch import CACHE,checksum
from route import features
from prepare import hashkey
# The R26 data preparation module uses the same short module name.
sys.modules.pop("prepare",None)
sys.path.insert(0,str(HERE.parents[1]/"graph_memory_round28/read_trigger"))
from serve import answer,Tokenizer,ENCT,WEIGHTS,ort
def put(name,data):
    p=HERE/name
    raw=json.dumps(data,sort_keys=True).encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
def main():
    view=json.loads(gzip.decompress((CACHE.parent/"projected/blind.json.gz").read_bytes()))
    route=json.loads((NATIVE/"route-seal.json").read_bytes())
    test=sorted(q for q,r in view.items() if not r["training"])
    lock={"q":test,"model":checksum(WEIGHTS),"tokenizer":checksum(ENCT),"prior":checksum(NATIVE/"route-seal.json"),
          "inputs":checksum(CACHE.parent/"projected/blind.json.gz"),"code":checksum(Path(__file__)),
          "protocol":checksum(HERE/"PROTOCOL_RU.md"),"n":len(test)}
    if (HERE/"plan.json").is_file():assert json.loads((HERE/"plan.json").read_bytes())==lock
    else:put("plan.json",lock)
    folder=CACHE.parent/("reader-"+checksum(HERE/"plan.json"));folder.mkdir(exist_ok=True)
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;options.add_session_config_entry("session.intra_op.allow_spinning","0")
    engine=ort.InferenceSession(str(WEIGHTS),sess_options=options,providers=["CPUExecutionProvider"]);tok=Tokenizer.from_file(str(ENCT))
    def solve(v,cache):
        bg,sit,question=v;parts=[];body=""
        for item in (sit,bg,question):
            start=len(body);body+=item;parts.append([start,len(body),start]);body+="\n\n"
        pred,calls,tokens=answer(tok,engine,question,body,parts,cache)
        return {"text":body[pred["start"]:pred["end"]] if pred else "","score":pred["score"] if pred else None,
                "calls":calls,"tokens":tokens,"windows":pred["windows"] if pred else None}
    records={}
    for ix,q in enumerate(test):
        point=folder/(q+".json");r=view[q]
        if not point.exists():
            cache={};old=solve(r["old"],cache)
            raw={**r,"prediction":old["text"]};basic,advanced,size,missing,_=features(raw)
            values={"random":0,"size":size,"missing":missing}
            for method,x in (("local",basic+advanced),("basic",basic)):
                m=route["fit"][method];values[method]=float((np.array(x)-m["mean"])/m["sd"]@np.asarray(m["beta"])+m["intercept"])
            t=perf_counter_ns();cold=solve(r["new"],cache);elapsed=perf_counter_ns()-t
            point.write_text(json.dumps({"old":old,"new":cold,"group":r["group"],"priority":values,"updated_ns":elapsed}),encoding="utf8")
        records[q]=json.loads(point.read_bytes())
        if (ix+1)%100==0:print(ix+1,flush=True)
    put("forecasts.json.gz",records);put("forecast-seal.json",{"forecasts":checksum(HERE/"forecasts.json.gz"),"plan":checksum(HERE/"plan.json")})
if __name__=="__main__":main()
