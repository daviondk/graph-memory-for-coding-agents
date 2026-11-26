"""Freeze paired learned models and address decisions before loading held-out labels."""
import sys
import numpy as np
from common import *

sys.path.insert(0,str(R51/"baseline"))
from study import fit_rank

def matrix(panel,ce):
    path,_=PANELS[panel]
    ranks=read(path/"orders.json.gz")
    lex=read((R50/"qa_replication/orders.json.gz") if panel=="train" else (path/"lex-orders.json.gz"))
    assert set(ranks)==set(lex)==set(ce)
    xs={}
    for q,r in ranks.items():
        ids=r["order"];l=lex[q];raw=ce[q]["scores"]
        assert set(str(i) for i in ids)==set(raw)
        sorted_ce=sorted(ids,key=lambda i:-raw[str(i)])
        xs[q]=np.array([[r["scores"][str(i)],1/(1+l["question_rank"][str(i)]),1/(1+l["snippet_rank"][str(i)]),
                          1/(1+j),raw[str(i)],1/(1+sorted_ce.index(i)),float(i in r["edges"])]
                         for j,i in enumerate(ids)])
    return ranks,xs

def fit(ce):
    ranks,xs=matrix("train",ce["train"])
    f=np.vstack([xs[q] for q in sorted(xs)])
    mean=f.mean(axis=0);scale=f.std(axis=0);scale[scale==0]=1
    x={q:(v-mean)/scale for q,v in xs.items()}
    gold=read(PANELS["train"][0]/"gold.json.gz")
    models={a:fit_rank(x,gold,ranks,n) for a,n in (("ce_hybrid",6),("ce_graph",7))}
    return dict(mean=mean.tolist(),scale=scale.tolist(),models=models,features=["cosine","reciprocal_question_rank","reciprocal_snippet_rank","reciprocal_dense_rank","ce_raw","reciprocal_ce_rank","mention"])

def decide(ce,model):
    base_choices={"2wiki":read(R51/"baseline/decisions.json.gz")["gate_confirmation"],
                  "hotpot":read(R51/"baseline/confirm/choices.json.gz")}
    pred={}
    for p in EVAL:
        ranks,xs=matrix(p,ce[p]);grp={}
        for q,r in ranks.items():
            ids=r["order"];xx=xs[q];base=base_choices[p][q]
            xs_std=(xx-model["mean"])/model["scale"]
            ce_order=sorted(ids,key=lambda i:-ce[p][q]["scores"][str(i)])
            row=dict(ce=ce_order[0],ce_linked=next((i for i in ce_order if i in r["edges"]),ce_order[0]),dense=r["dense"],
                     linked_dense=r["linked_dense"],r51_graph=base["graph"],r51_hybrid=base["hybrid"])
            for a,z in model["models"].items():
                w=z["coef"];row[a]=ids[int(np.argmax(xs_std[:,:len(w)]@w))]
            grp[q]=row
        pred[p]=grp
    return pred

def main():
    assert sha(D/"ce-scores.json.gz")==get("ce-seal.json")["scores"]
    src=get("ce-scores.json.gz");model=fit(src);pred=decide(src,model)
    put("model.json",model);put("choices.json.gz",pred)
    put("decision-seal.json",dict(model=sha(D/"model.json"),choices=sha(D/"choices.json.gz"),ce=sha(D/"ce-seal.json"),
        train=sha(PANELS["train"][0]/"gold.json.gz"),code=sha(Path(__file__))))
if __name__=="__main__":main()

