from common import D,BASE,DATA,raw,digest,put,source
from hotpot_cardinality import features
import numpy as np

def main():
    weights=raw(BASE/"model.json")
    lock={"model":digest(BASE/"model.json"),"protocol":digest(D/"PROTOCOL_RU.md"),"selector":digest(D/"select_frozen.py"),
          "ranks":{p:{f:digest(path/f) for f in ("orders.json.gz","lex-orders.json.gz")} for p,(path,_) in DATA.items()}}
    put("plan.json",lock)
    pred={}
    for p,(path,_) in DATA.items():
        prev=raw(BASE/"confirm/choices.json.gz") if p=="hotpot" else raw(BASE/"decisions.json.gz")["gate_confirmation"]
        ranks,lex=raw(path/"orders.json.gz"),raw(path/"lex-orders.json.gz")
        rows={}
        for q,r in ranks.items():
            ids=r["order"];x=(features(r,lex[q])-weights["mean"])/weights["scale"]
            w=weights["graph"]["coef"]
            scores=x[:,:4]@w[:4]
            a=ids[int(np.argmax(x@w))];b=ids[int(np.argmax(scores))]
            h=ids[int(np.argmax(x[:,:4]@weights["hybrid"]["coef"]))]
            assert a==prev[q]["graph"] and h==prev[q]["hybrid"]
            edges=bool(r["edges"])
            assert edges or a==b
            rows[q]={"graph":a,"masked":b,"hybrid":h,"edge":edges}
        assert len(rows)==1280
        pred[p]=rows
    put("choices.json.gz",pred)
    put("decision-seal.json",{"choices":digest(D/"choices.json.gz"),"plan":digest(D/"plan.json")})
    print("Sealed",sum(map(len,pred.values())),"choices")
if __name__=="__main__": main()
