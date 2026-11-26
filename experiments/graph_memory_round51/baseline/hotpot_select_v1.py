"""Use only a frozen model and visibility-only rank files for transfer decisions."""
import hashlib
import json
from study import HERE, raw, save, features, digest, CUTOFF
import numpy as np

TRANSFER = HERE.parent / "transfer"


def decisions(ranks, lex, model):
    result = {}
    for q,r in sorted(ranks.items()):
        x = (features(r,lex[q])-model["mean"])/model["scale"]
        ids=r["order"]
        a,b = r["dense"],r["linked_dense"]
        j=ids.index(b)
        z = r["scores"][str(a)]-r["scores"][str(b)]
        row={"dense":a,"linked":b,"gate":b if z<=CUTOFF else a}
        assert row["gate"]==r["adaptive"]
        for name in ("graph","hybrid"):
            weights=model[name]["coef"]
            score=x[:,:len(weights)]@weights
            row[name]=ids[int(np.argmax(score))]
            row[name+"_pair"]=b if score[j]>score[0] else a
        f = model["answer_gain"]
        value=(x[j,:4]-x[0,:4])@f["coef"]+f["intercept"]
        row["answer_pair"]=b if value>0 else a
        result[q]=row
    return result


if __name__=="__main__":
    paths=[HERE/"HOTPot_PROTOCOL_RU.md",HERE/"model.json",HERE/"study.py",HERE/"hotpot_select.py",
           TRANSFER/"orders.json.gz",TRANSFER/"lex-orders.json.gz",TRANSFER/"threshold-seal.json",TRANSFER/"projection-seal.json"]
    pinned={p.relative_to(HERE.parent).as_posix(): digest(p) for p in paths}
    sealname="hotpot-plan-seal.json"
    if (HERE/sealname).exists():
        assert raw(HERE/sealname)==pinned
    else:
        save(sealname,pinned)
    r=raw(TRANSFER/"orders.json.gz"); lex=raw(TRANSFER/"lex-orders.json.gz")
    assert len(r)==640 and set(r)==set(lex)
    preds=decisions(r,lex,raw(HERE/"model.json"))
    save("hotpot-decisions.json.gz",preds)
    save("hotpot-decision-seal.json",{"plan":digest(HERE/sealname),"choices":digest(HERE/"hotpot-decisions.json.gz"),
                                    "n":len(preds),"test_inputs":["orders","lex-orders"]})
    print("Sealed",len(preds),digest(HERE/"hotpot-decisions.json.gz"))
