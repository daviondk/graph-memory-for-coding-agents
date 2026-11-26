"""Independent endpoint recomputation, policy guard checks, and split-disjointness verification."""
from collections import Counter
from large_panel import HERE,CONF,S,C_S,DEV,GP,read,save,hashfile,canon
from large_predictions import ARMS
from grade_confirmation import title

def main():
    seal=read(HERE/"prediction-seal.json")
    assert all(hashfile(HERE/k)==h for k,h in seal["local"].items())
    pred=read(HERE/"predictions.json.gz")
    names=read(HERE/"chosen-titles.json.gz");gold=read(HERE/"support.json.gz")
    scores=read(HERE/"results.json")["independent_12000"]
    counted=Counter();evidence=Counter();delta=Counter();switched=Counter()
    pidx,sidx,treeidx=map(ARMS.index,("learned_dev","coord_or_same_as","dev_tree"))
    for q,r in pred.items():
        g=set(gold[q][1]);src=title(names[str(r["seed"])][1])
        for i,mode in enumerate(ARMS):
            retrieved={src,title(names[str(r["choices"][i])][1])}
            counted[mode]+=int(g.issubset(retrieved))
            evidence[mode]+=sum(v in retrieved for v in g)/len(g)
        for j,k in ((pidx,sidx),(pidx,treeidx)):
            a,b=r["choices"][j],r["choices"][k]
            if a!=b:switched[ARMS[k]]+=1
    assert dict(counted)==scores["complete"] and all(abs(evidence[m]/len(pred)-scores["recall"][m])<1e-12 for m in ARMS)
    for target in ("coord_or_same_as","dev_tree"):
        assert switched[target]==scores["contrasts"]["learned_dev vs "+target]["switched"]
    qnew=read(S/"questions.json.gz");qold=read(DEV/"questions.json.gz")|read(C_S/"questions.json.gz")
    assert set(qnew).isdisjoint(qold) and {canon(v) for v in qnew.values()}.isdisjoint(canon(v) for v in qold.values())
    prof={r["seed"] for r in pred.values()}
    old=set();oldnames=set()
    for base in (GP,CONF):
        text=read(base/"chosen-titles.json.gz")
        rs={r["seed"] for r in read(base/"predictions.json.gz").values()}
        old|=rs;oldnames|={canon(text[str(i)][1]) for i in rs}
    assert prof.isdisjoint(old) and {canon(names[str(i)][1]) for i in prof}.isdisjoint(oldnames)
    save(HERE/"verification.json",{"status":"PASS","questions":len(pred),"address_clusters":len(prof),
         "question_id_and_text_overlap":0,"seed_id_and_title_overlap":0,"complete_and_recall":"recomputed 84000 pair results",
         "seal":hashfile(HERE/"prediction-seal.json")})
    print("PASS",len(pred),len(prof))

if __name__=="__main__":main()

