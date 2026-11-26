"""Compare identical information budgets and persist each chosen catalogue ID before grading."""
from collections import Counter
from large_panel import HERE,S,CONF,GT,GP,C_S,read,save,hashfile,tokens
from large_model import surface,predict
from syntax import features

ARMS=["learned_dev","coord_cautious","coord_or_same_as","dev_tree","primary_href","primary_text","href_first"]
def score(question,first_title,gate,href,text,model,tree):
    d,n,*_=gate
    conj,x=features(question,first_title,gate)
    syntax=surface(question,first_title)
    logit=model["intercept"]+sum(v*w for v,w in zip(x,model["coef"]))>=0
    dt=bool(predict(x,tree))
    method=[d if n and b else href for b in (logit,bool(conj),syntax,dt,True)]
    method.extend([d if n else text,href])
    return {"choices":method,"direct":bool(n),"coordination":bool(conj),"surface":syntax,"direct_logit":bool(logit and n),"direct_tree":bool(dt and n)}

def main():
    qtext=read(S/"questions.json.gz");opened=read(S/"opened.json.gz")
    model=read(CONF/"dev-model.json");tree=read(HERE/"dev-tree.json")
    assert tree["code"]==hashfile(HERE/"large_model.py") and tree["protocol"]==hashfile(HERE/"PROTOCOL_RU.md")
    assert tree["frozen_linear"]==hashfile(CONF/"dev-model.json") and model["feature_code"]==hashfile(CONF/"syntax.py")
    def table(file):return {q:list(map(int,v)) for q,*v in (l.split("\t") for l in (S/file).read_text().splitlines())}
    seconds=table("second.tsv");gates=table("policy52-direct.tsv");inputs=table("seed.tsv")
    assert set(seconds)==set(gates)==set(inputs)==set(qtext) and len(qtext)==12000
    selected={};needed=set();routes=Counter()
    for q,question in qtext.items():
        seed,free,raw,_,_,_,text,href,*_=seconds[q]
        assert seed==gates[q][0]==inputs[q][0]
        gate=gates[q][8:14]
        row=score(question,opened[str(seed)]["title"],gate,href,text,model,tree)
        assert len(row["choices"])==len(ARMS) and seed not in row["choices"] and min(row["choices"])>=0
        if not gate[1]:
            assert row["choices"]==[href]*5+[text,href]
        assert not row["coordination"] or row["surface"]
        routes.update({k:int(v) for k,v in row.items() if k!="choices"})
        row.update(seed=seed,gate=gate)
        selected[q]=row;needed.update([seed,*row["choices"],*([gate[0]] if gate[1] else [])])
    names={}
    with (S/"titles.txt").open(encoding="utf8") as f:
        for i,l in enumerate(f):
            if i in needed:
                page,title=l.rstrip("\n").split("\t",1);names[i]=[int(page),title]
    assert set(names)==needed
    for q,r in selected.items():
        d,n,a,b,_,_=r["gate"]
        if n:
            qt=tokens(qtext[q]);st=tokens(names[r["seed"]][1]);dt=tokens(names[d][1]);assert qt[a:b]==dt
            starts=[j for j in range(len(qt)) if qt[j:j+len(st)]==st];assert starts and all(j+len(st)<=a or b<=j for j in starts)
    save(HERE/"predictions.json.gz",selected);save(HERE/"chosen-titles.json.gz",names)
    files=["PROTOCOL_RU.md","sampling.json","panel.json","kernel.json","opening.json","dev-tree.json","large_panel.py","large_model.py",
           "run_pipeline.py","large_predictions.py","predictions.json.gz","chosen-titles.json.gz"]
    save(HERE/"prediction-seal.json",{"n":len(selected),"arms":ARMS,"routes":routes,"local":{k:hashfile(HERE/k) for k in files},
              "cache":{k:hashfile(S/k) for k in ("seed.tsv","second.in","second.tsv","policy52-direct.tsv","questions.in","opened.json.gz")},
              "previous_seal":hashfile(CONF/"prediction-seal.json"),"frozen_logit":hashfile(CONF/"dev-model.json")})
    print("SEALED",len(qtext),dict(routes),hashfile(HERE/"prediction-seal.json"))
if __name__=="__main__":main()

