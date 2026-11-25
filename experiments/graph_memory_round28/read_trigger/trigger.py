"""Freeze an online admission rule with features measured before the extra read."""
import hashlib
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/"revoked_evidence"))
from capture import PREVIOUS,P,ENCT,Tokenizer,mappings,read,save,sha
CHOICES=ROOT/"graph_memory_round25/directional_open/squad-choices.json.gz"
def hashkey(salt,value):return hashlib.sha256((salt+"/"+value).encode()).digest()
def routing(p,parts,cut):
    l,h=p["start"],p["end"];a,b,_=parts[p["body_index"]]
    assert a<=l<h<=b
    edge=min(l-a,b-h);inside=bool(cut and cut["l"]<=l and h<=cut["h"])
    distance=max(cut["l"]-h,l-cut["h"],0) if cut else 100000
    left,right=cut["matches"] if cut else (0,0)
    return [p["score"],p["answer_tokens"],p["body_index"],len(parts),p["windows"],np.log1p(edge),np.log1p(b-a),
            np.log1p(distance),int(inside),left,right,int(cut is not None),np.log1p(h-l)]
def new_work(tok,query,source,base,extra):
    def keys(parts):
        return [(hashlib.sha256(ids.astype("<i8").tobytes()).digest()+hashlib.sha256(mask.tobytes()).digest(),len(ids))
                for ids,_,seg,l,r,mask in mappings(tok,query,source,parts)]
    before=keys(base);after=keys(base+extra);known={k for k,n in before}
    return [sum(n for k,n in before),sum(n for k,n in after),sum(n for k,n in after if k not in known)]
def prepare():
    context=read(PREVIOUS/"contexts.json.gz");pred=read(PREVIOUS/"predictions.json.gz")
    source=read(P/"blind-input.json.gz");cuts=read(CHOICES);tok=Tokenizer.from_file(str(ENCT))
    titles=sorted({r["title"] for r in context.values()},key=lambda t:hashkey("trigger-article-v1",t))
    train=set(titles[:24]);rows={};costs={}
    for q,r in context.items():
        title,query=source["qs"][q];base=r["base"];old=pred[q]["arms"]["base"]
        rows[q]={"training":title in train,"title":title,"x":routing(old,base,cuts[q]["cut"])}
        pricing=new_work(tok,query,source["docs"][title],base,r["arms"]["both"]["extra"])
        assert pricing[:2]==[old["logical_tokens"],pred[q]["arms"]["both"]["logical_tokens"]]
        costs[q]={"model":pricing,"extra":r["arms"]["both"]["native_extra"],"ranges":len(r["arms"]["both"]["extra"])}
    save(HERE/"observations.json.gz",rows);save(HERE/"costs.json.gz",costs)
    score=read(PREVIOUS/"per-query.json.gz")
    targets={q:[score[q]["arms"][m]["f1"] for m in ("base","both")] for q,r in rows.items() if r["training"]}
    assert len(targets)==288
    save(HERE/"train-labels.json.gz",targets)
    save(HERE/"input-seal.json",{"protocol":sha(HERE/"PROTOCOL_RU.md"),"script":sha(Path(__file__)),
         "before":sha(HERE/"observations.json.gz"),"cost":sha(HERE/"costs.json.gz"),
         "training_labels":sha(HERE/"train-labels.json.gz"),"test_articles":titles[24:]})
def fit():
    rows=read(HERE/"observations.json.gz");targets=read(HERE/"train-labels.json.gz");train=sorted(targets)
    test=sorted(q for q in rows if not rows[q]["training"]);assert len(test)==len(train)==288
    assert not ({rows[q]["title"] for q in train}&{rows[q]["title"] for q in test})
    xs=np.array([rows[q]["x"] for q in train]);mu=xs.mean(axis=0);std=xs.std(axis=0);std[std<1e-8]=1.
    x=(xs-mu)/std
    def coefficients(ys):
        ys=np.array(ys);return ys.mean(),np.linalg.solve(x.T@x+20*np.eye(x.shape[1]),x.T@(ys-ys.mean()))
    coeff={"gain":coefficients([targets[q][1]-targets[q][0] for q in train]),
           "error":coefficients([1-targets[q][0] for q in train])}
    def score(q):
        v=np.array(rows[q]["x"])
        return {"hash":int.from_bytes(hashkey("trigger-random",q)[:8],"big")/2**64,
             "low_score":-v[0],"near_edge":-v[5],**{name:float(mean+((v-mu)/std)@coef) for name,(mean,coef) in coeff.items()}}
    train_scores={q:score(q) for q in train};test_scores={q:score(q) for q in test};names=list(score(test[0]))
    threshold={m:float(np.median([r[m] for r in train_scores.values()])) for m in names}
    batches={m:set(sorted(test,key=lambda q:(-test_scores[q][m],hashkey("trigger-tie",q)))[:144]) for m in names}
    output={q:{"title":rows[q]["title"],"scores":test_scores[q],
               "online":{m:int(test_scores[q][m]>=threshold[m]) for m in names},
               "batch":{m:int(q in batches[m]) for m in names}} for q in test}
    save(HERE/"routes.json.gz",output)
    save(HERE/"route-seal.json",{"inputs":sha(HERE/"input-seal.json"),"threshold":threshold,"routes":sha(HERE/"routes.json.gz"),
         "coef":{k:[float(a),b.tolist()] for k,(a,b) in coeff.items()}})
if __name__=="__main__":
    prepare();fit()

