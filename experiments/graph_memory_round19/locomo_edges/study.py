"""Use the authors' LRE classifier/scorer. The only intervention is the seven additional columns."""
import collections
import gzip
import hashlib
import itertools
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

for v in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[v]="1"
import numpy as np
import sklearn
HERE=Path(__file__).resolve().parent
REF=Path(os.environ.get("LRE_REPO","D:/CodexResearch/x20-lre-reference"))
DATA=Path(os.environ.get("LOCOMO_FILE",str(REF/"data/reference-locomo10.json")))
REV="1aa51d672d772b27a272cab1393cd9968c13d158"
DATA_SHA="79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
sys.path.insert(0,str(REF))
from experiments.conversational_qa import dataset as ds,lre_qa as native

EXTRA=("has_prior","speaker_change","prior_asked","both_asked","prior_loglen","answer_len","overlap")

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def edge(t,p):
    if p is None:return [0.]*7
    left=set(re.findall(r"\w+",p.text.casefold()))
    right=set(re.findall(r"\w+",t.text.casefold()))
    change=t.speaker!=p.speaker
    prev=change and "?" in p.text
    return list(map(float,[1,change,prev,prev and "?" in t.text,math.log1p(len(p.text.split())),
            prev*math.log1p(len(t.text.split())),len(left&right)/max(1,len(left|right))]))

def predict():
    assert sha(DATA)==DATA_SHA
    assert subprocess.check_output(["git","-C",str(REF),"rev-parse","HEAD"],text=True).strip()==REV
    lock=dict(dataset=sha(DATA),upstream=REV,code=sha(Path(__file__)),protocol=sha(HERE/"PROTOCOL_RU.md"),
              native={f:sha(REF/"experiments/conversational_qa"/f) for f in ("dataset.py","lre_qa.py","run_retrieval_auc.py")},
              sklearn=sklearn.__version__,numpy=np.__version__,python=sys.version)
    (HERE/"input-lock.json").write_text(json.dumps(lock,indent=2),encoding="utf-8")
    rows,_=ds.load_groups("locomo",locomo_path=str(DATA))
    qcs=ds.load_locomo(str(DATA))
    conv=ds.conv_groups(qcs)
    lookup={}
    for cid,q in conv.items():
        grouped=collections.defaultdict(list)
        for t in q[0].turns:grouped[t.session_num].append(t)
        for ts in grouped.values():
            prevs=ts[:-1]
            for i,t in enumerate(ts):
                actual=prevs[i-1] if i else None
                sham=prevs[(i-1+len(prevs)//2)%len(prevs)] if i else None
                lookup[str(cid),t.dia_id]=(edge(t,actual),edge(t,sham))
    assert len(lookup)==len(rows)
    families={}
    removed={}
    orig=native.TRAJ_KEYS
    try:
        for nm,side in [("original",None),("edge",0),("shifted",1)]:
            native.TRAJ_KEYS=orig if side is None else orig+list(EXTRA)
            table=rows if side is None else [ds.Row(r.text,r.label,r.group,r.key,
               dict(r.traj,**dict(zip(EXTRA,lookup[r.group,r.key][side],strict=True)))) for r in rows]
            families[nm],removed[nm]=native.lre_scores(table,fuse=True,dedup=True)
    finally:
        native.TRAJ_KEYS=orig
    assert len(set(removed.values()))==1
    record=[dict(group=r.group,key=r.key,score={k:float(a[i]) for k,a in families.items()}) for i,r in enumerate(rows)]
    path=HERE/"forecasts.json.gz"
    path.write_bytes(gzip.compress(json.dumps(record,separators=(",",":")).encode(),mtime=0))
    (HERE/"forecast-lock.json").write_text(json.dumps(dict(forecast=sha(path),removed_train_rows=removed,
            input=sha(HERE/"input-lock.json"),n=len(rows),n_questions=len(qcs)),indent=2),encoding="utf-8")

def paired(delta):
    d=np.array(delta)
    null=np.array([np.mean(d*np.array(s)) for s in itertools.product((-1,1),repeat=len(d))])
    rng=np.random.default_rng(13)
    ci=np.quantile(np.mean(d[rng.integers(0,len(d),(10000,len(d)))],axis=1),[.025,.975])
    return dict(mean=float(d.mean()),lo=float(ci[0]),hi=float(ci[1]),individual=d.tolist(),
                signflip_p=float(np.mean(abs(null)>=abs(d.mean())-1e-14)))

def score():
    lock=json.loads((HERE/"forecast-lock.json").read_bytes())
    assert sha(HERE/"forecasts.json.gz")==lock["forecast"] and sha(DATA)==DATA_SHA
    raw=json.loads(gzip.decompress((HERE/"forecasts.json.gz").read_bytes()))
    rows,_=ds.load_groups("locomo",locomo_path=str(DATA))
    assert [(r.group,r.key) for r in rows]==[(x["group"],x["key"]) for x in raw]
    groups=sorted({r.group for r in rows})
    out={}
    def measure(rows,s):
        rec=native.recall_at_budget(rows,s)
        return {"auc":native.per_group_auc(rows,s)[0],**{"recall_"+str(b):x for b,x in rec.items()}}
    for nm in ("original","edge","shifted"):
        s=np.array([x["score"][nm] for x in raw])
        by={}
        for gr in groups:
            idx=[i for i,r in enumerate(rows) if r.group==gr]
            by[gr]=measure([rows[i] for i in idx],s[idx])
        avg=measure(rows,s)
        assert all(abs(avg[k]-np.mean([v[k] for v in by.values()]))<1e-12 for k in avg)
        out[nm]=dict(macro=avg,by=by)
    contrasts={b:{m:paired([out["edge"]["by"][g][m]-out[b]["by"][g][m] for g in groups]) for m in out[b]["macro"]}
               for b in ("original","shifted")}
    gold=[(r.group,r.key,r.label) for r in rows]
    (HERE/"labels.json.gz").write_bytes(gzip.compress(json.dumps(gold,separators=(",",":")).encode(),mtime=0))
    output=dict(methods=out,contrasts=contrasts,turns=len(rows),gold_turns=sum(r.label for r in rows),
                conversations=groups,questions=lock["n_questions"],train_removed=lock["removed_train_rows"])
    (HERE/"results.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(output["turns"],output["gold_turns"],output["questions"]);print({k:v["macro"] for k,v in out.items()})
    print("primary",contrasts["original"]["recall_0.2"],"placebo",contrasts["shifted"]["recall_0.2"])
if __name__=="__main__":
    {"predict":predict,"score":score}[sys.argv[1]]()

