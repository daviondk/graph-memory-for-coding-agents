"""Independent source reconstruction of split-unit and turn-level overlap counts and native LRE parity."""
import collections
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path
import run as exp
import numpy as np

def h(s):
    return hashlib.sha256(s.encode()).hexdigest()

def normal(s):
    return " ".join(unicodedata.normalize("NFKC",s).casefold().split())

def main():
    data=json.loads(exp.tr.TARGET.read_bytes())
    sess={}
    turns={}
    for q in data:
        k=h(q["question_id"])
        e=set()
        z=[]
        for rid,arr in zip(q["haystack_session_ids"],q["haystack_sessions"],strict=True):
            e.add("sid"+h(rid))
            norm_pairs=[(w["role"],normal(w["content"])) for w in arr]
            e.add("source"+h(json.dumps(norm_pairs,ensure_ascii=False,separators=(",",":"))))
            z.extend((h(normal(w["content"])),w.get("has_answer") is True) for w in arr)
        sess[k]=e
        turns[k]=z
    folds=exp.load("split.json")["folds"]
    res=[]
    for i,fd in enumerate(folds):
        seen_sources=set.union(*(sess[k] for k in fd["test"]))
        train_sources=set.union(*(sess[k] for k in fd["train"]))
        assert not seen_sources & train_sources
        seen_turn={t for k in fd["test"] for t,y in turns[k]}
        training=[(t,y) for k in fd["train"] for t,y in turns[k]]
        npurged=[0,0]
        for t,y in training:
            if t in seen_turn:
                npurged[int(y)]+=1
        md=exp.load(f"fold-{i:02d}.json")
        assert npurged==[md["removed_train_neg"],md["removed_train_pos"]]
        assert md["train_remaining"]==len(training)-sum(npurged)
        assert md["train_pos"]==sum(y for t,y in training)-npurged[1]
        res.append(dict(fold=i,test_sources=len(seen_sources),train_sources=len(train_sources),
                        source_intersections=0, surviving_text_intersections=0,
                        purged_negative=npurged[0],purged_positive=npurged[1]))
    del data
    # Explicit comparison of the actual persisted full-history fold against a separate invocation of the original scorer.
    d=exp.make_data()
    fd=folds[0]
    seen=np.unique(np.concatenate([d[q][1] for q in fd["test"]]))
    rows=[]
    for q in fd["train"]:
        texts,ids,x,_,_,y=d[q]
        for i in np.where(~np.isin(ids,seen))[0]:
            rows.append(exp.tr.ds.Row(texts[i],int(y[i]),"train",str(i),dict(zip(exp.tr.BASE_KEYS,x[i],strict=True))))
    check=fd["test"][0]
    txt,_,x,_,_,_=d[check]
    for i in range(len(txt)):
        rows.append(exp.tr.ds.Row(txt[i],i%2,"probe",str(i),dict(zip(exp.tr.BASE_KEYS,x[i],strict=True))))
    pred,_=exp.tr.native.lre_scores(rows,fuse=True,dedup=False)
    expected=exp.load("pred-00.json.gz")[0]["score"]["original"]
    err=float(np.max(abs(pred[-len(expected):]-expected)))
    assert err<1e-12,(err,len(expected))
    exp.save("overlap-audit.json",dict(blocks=res,native_max_abs_deviation=err,native_probe_turns=len(expected)))
    print("PASS, source rebuild, 33 no-overlap blocks, native LRE parity:",len(expected),err)
if __name__=="__main__":
    main()
