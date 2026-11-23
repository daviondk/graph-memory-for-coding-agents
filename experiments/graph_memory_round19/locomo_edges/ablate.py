"""Fixed feature subsets for an exploratory check on the same LoCoMo folds."""
import collections
import gzip
import json
from study import DATA,DATA_SHA,HERE,EXTRA,edge,ds,native,np,paired,sha

def main():
    assert sha(DATA)==DATA_SHA
    rows,_=ds.load_groups("locomo",locomo_path=str(DATA))
    turns={}
    for cid,qcs in ds.conv_groups(ds.load_locomo(str(DATA))).items():
        prev=None
        for t in qcs[0].turns:
            actual=prev if prev and prev.session_num==t.session_num else None
            turns[str(cid),t.dia_id]=dict(zip(EXTRA,edge(t,actual),strict=True))
            prev=t
    table=[ds.Row(r.text,r.label,r.group,r.key,dict(r.traj,**turns[r.group,r.key])) for r in rows]
    original=list(native.TRAJ_KEYS)
    scopes={"structure":[0,1],"structure_question":[0,1,2,3,5],"structure_surface":[0,1,4,6]}
    scores={}
    try:
        for name,idx in scopes.items():
            native.TRAJ_KEYS=original+[EXTRA[i] for i in idx]
            scores[name],_=native.lre_scores(table,fuse=True,dedup=True)
    finally:
        native.TRAJ_KEYS=original
    preds=[dict(group=r.group,key=r.key,score={k:float(s[i]) for k,s in scores.items()}) for i,r in enumerate(rows)]
    f=HERE/"ablation-forecasts.json.gz"
    f.write_bytes(gzip.compress(json.dumps(preds,separators=(",",":")).encode(),mtime=0))
    baseline=json.loads((HERE/"results.json").read_bytes())["methods"]
    by={}; contrasts={}
    for name,s in scores.items():
        m={"auc":native.per_group_auc(rows,s)[0],**{"recall_"+str(b):v for b,v in native.recall_at_budget(rows,s).items()}}
        groups={}
        for g in sorted({r.group for r in rows}):
            ids=[i for i,r in enumerate(rows) if r.group==g];rr=[rows[i] for i in ids]
            groups[g]={"auc":native.per_group_auc(rr,s[ids])[0],
                       **{"recall_"+str(b):v for b,v in native.recall_at_budget(rr,s[ids]).items()}}
        by[name]=dict(macro=m,by=groups)
        contrasts[name]={k:paired([groups[g][k]-baseline["original"]["by"][g][k] for g in groups]) for k in m}
    obj=dict(methods=by,vs_original=contrasts,subsets={k:[EXTRA[i] for i in ix] for k,ix in scopes.items()},
             protocol=sha(HERE/"ABLATION_RU.md"),code=sha(HERE/"ablate.py"),base=sha(HERE/"forecast-lock.json"),
             predictions=sha(f))
    (HERE/"ablation-results.json").write_text(json.dumps(obj,indent=2),encoding="utf-8")
    print({k:m["macro"] for k,m in by.items()})
if __name__=="__main__":main()

