from collections import Counter,defaultdict
import hashlib
import os
import re
import sys
import time
from pathlib import Path
os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["MKL_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
from features import ROOT,TRAINED,ONLINE,stream,load,save,sha,rows,tool_lookup,design,POSITION,SHAPE
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
sys.path.insert(0,str(TRAINED))
from prepare import N,RAW,pilot,OFF,adapt_isetrace_record,parse_isetrace_record,RUN

def plan():
    split=load(TRAINED/"split.json.gz");orig=load(TRAINED/"protocol-seal.json")
    assert sha(TRAINED/"split.json.gz")==orig["split.json.gz"]
    unique={k:{r["t"] for r in arr} for k,arr in split.items()}
    assert not (unique["train"]&unique["test"] or unique["train"]&unique["dev"] or unique["test"]&unique["dev"])
    t=sorted(unique["train"],key=lambda s:hashlib.sha256(("r19-write-learn|"+s).encode()).digest())[:256]
    assert len(t)==256
    inputs={f.name:sha(f) for f in (ROOT/"PROTOCOL_RU.md",ROOT/"features.py",ROOT/"train_write.py",ROOT/"forecast_write.py",
        TRAINED/"split.json.gz",ONLINE/"predict.py",ONLINE/"byte_memory.py",ONLINE/"forecast-lock.json",ONLINE/"bytes-lock.json")}
    save(ROOT/"plan.json",{"selection":t,"inputs":inputs,"by_split":{k:len(v) for k,v in unique.items()},
        "train_projection_sha":{tid:sha(RUN/"projection/train"/(tid+".json.gz")) for tid in t}})
def run():
    start=time.perf_counter()
    selection=load(ROOT/"plan.json");ids=set(selection["selection"])
    splits=load(TRAINED/"split.json.gz");by=defaultdict(set)
    for r in splits["train"]:
        if r["t"] in ids:by[r["t"]].add(r["q"])
    qids={q for qs in by.values() for q in qs};assert len(by)==len(ids)
    # Selected train-query records alone are validated or passed to gold resolution.
    examples={q["id"]:N._QUERY_ADAPTER.validate_python(q) for _,q in pilot.stream(pilot.Q) if q["id"] in qids}
    locks={r["path"]:r["sha256"] for r in load(OFF/"source-lock.json")}
    pattern=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"')
    tok=stream.Tokenizer.from_file(str(stream.TOKENIZER))
    X=[];labels=[];names=[];info=[];evidence={}
    for shard in range(8):
        path=RAW/f"trajectories-{shard:05d}.jsonl";assert sha(path)==locks["trajectories/"+path.name]
        with path.open("rb") as fp:
            for raw in fp:
                m=pattern.search(raw);assert m is not None
                t=m.group(1).decode()
                if t not in by:continue
                if t not in ids:raise ValueError("duplicate train ID")
                ids.remove(t)
                priorp=RUN/"projection/train"/(t+".json.gz")
                assert sha(priorp)==selection["train_projection_sha"][t]
                prior=load(priorp)
                assert prior["digest"]==hashlib.sha256(raw).hexdigest()
                import json
                tr=adapt_isetrace_record(parse_isetrace_record(json.loads(raw)),source_revision=pilot.RAW[1]);assert tr.trajectory_id==t
                fields={**{e.event_id:e.raw_arguments for e in tr.tool_calls},**{e.event_id:e.content for e in tr.tool_outputs}}
                address,blocks,_,_=stream.stream_blocks(fields,prior["pool"],tok)
                terms=defaultdict(list);bounds={}
                for q in sorted(by[t]):
                    ex=examples[q];match=N._match_task_text(ex,tr);assert match is not None
                    spans=N._resolve_gold_spans(ex,match);bounds[q]=[s.model_dump() for s in spans]
                    for s in spans:terms[s.event_id,s.json_pointer].append((s.char_start,s.char_end))
                y=[int(any(max(a,l)<min(b,h) for l,h in terms[tuple(address[e])])) for e,a,b,c,n in blocks];assert sum(y)>0
                z,tool=rows(address,blocks,fields,tool_lookup(prior["pool"]))
                X.append(z);names.extend(tool);labels.extend(y)
                evidence[t]={"q":bounds,"base_projection_sha":selection["train_projection_sha"][t],"raw_record":prior["digest"]}
                info.append({"t":t,"q":len(bounds),"blocks":len(y),"positive":sum(y)})
        print("train shard",shard,len(info),flush=True)
    assert not ids and len(qids)==sum(r["q"] for r in info)
    x=np.concatenate(X);y=np.asarray(labels,dtype=np.int8)
    vocab=sorted(Counter(names),key=lambda s:(-names.count(s),s))[:32]
    model={"tools":vocab,"feature_names":POSITION+SHAPE+["tool="+t for t in vocab],"arms":{}}
    for arm,full in (("positional",False),("full",True)):
        design_x=design(x,names,vocab,full);scaler=StandardScaler().fit(design_x)
        fit=LogisticRegression(C=1,max_iter=600,solver="lbfgs",random_state=13).fit(scaler.transform(design_x),y)
        assert fit.n_iter_[0]<600
        model["arms"][arm]={"means":scaler.mean_.tolist(),"scale":scaler.scale_.tolist(),"intercept":float(fit.intercept_[0]),
            "coefficients":fit.coef_[0].tolist(),"iterations":int(fit.n_iter_[0])}
    save(ROOT/"model.json",model);save(ROOT/"train-evidence.json.gz",evidence)
    save(ROOT/"train-statistics.json",{"by_trajectory":info,"queries":len(qids),"n":len(y),"positive":int(y.sum()),
        "seconds":time.perf_counter()-start,"sklearn":sklearn.__version__,"numpy":np.__version__})
    save(ROOT/"model-seal.json",{n:sha(ROOT/n) for n in ("plan.json","model.json","train-evidence.json.gz","train-statistics.json")})
    print("training",len(y),int(y.sum()),len(qids),time.perf_counter()-start,flush=True)
if __name__=="__main__":{"lock":plan,"train":run}[sys.argv[1]]()
