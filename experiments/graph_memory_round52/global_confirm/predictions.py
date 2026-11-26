"""Apply frozen rules on the clean first-address set; inspect no annotations."""
from panel import HERE,S,DEV,GP,GT,read,save,hashfile,tokens
from syntax import choose, ARMS
from collections import Counter

def table(name):
    return {q:list(map(int,rest)) for q,*rest in (l.split("\t") for l in (S/name).read_text().splitlines())}

def main():
    model=read(HERE/"dev-model.json")
    assert model["feature_code"]==hashfile(HERE/"syntax.py") and model["registration"]==hashfile(HERE/"PROTOCOL_RU.md")
    qs=read(S/"questions.json.gz");opened=read(S/"opened.json.gz")
    second=table("second.tsv");direct=table("policy52-direct.tsv");seeds=table("seed.tsv")
    assert set(qs)==set(second)==set(seeds)==set(direct)==set(read(HERE/"panel.json")["ids_in_hash_order"])
    output={};counts=Counter();named=set()
    for q,question in qs.items():
        seed,free,raw,_,_,_,text,href,*_=second[q]
        assert seed==seeds[q][0]==direct[q][0]
        gate=direct[q][8:14]; assert len(gate)==6
        addr=gate[0];source=opened[str(seed)]
        pred,conj,learned=choose(question,source["title"],gate,raw,href,text,free,model)
        assert len(pred)==len(ARMS) and min(pred)>=0 and seed not in pred
        if addr>=0:
            assert pred[0]==pred[1]==addr and gate[1]>0
            counts["primary_direct"]+=1
        else:
            assert pred[0]==href and pred[1]==text and not learned
        if not conj:assert pred[5]==pred[6]==pred[7]==href
        if pred[0]!=pred[7]:assert addr>=0 and not conj
        if conj:counts["coordination"]+=1
        if learned:counts["learned_direct"]+=1
        output[q]={"seed":seed,"choices":pred,"direct_gate":gate,"coordination":conj,"learned_direct":learned}
        named.update([seed,*pred,*([addr] if addr>=0 else [])])
    names={}
    with (S/"titles.txt").open(encoding="utf8") as f:
        for i,l in enumerate(f):
            if i in named:
                page,title=l.rstrip("\n").split("\t",1)
                names[i]=[int(page),title]
    assert set(names)==named
    for q,r in output.items():
        addr,opts,a,b,_,_=r["direct_gate"]
        if opts:
            question=tokens(qs[q]);seed=tokens(names[r["seed"]][1]);title=tokens(names[addr][1])
            assert question[a:b]==title and seed
            starts=[j for j in range(len(question)) if question[j:j+len(seed)]==seed]
            assert starts and all(j+len(seed)<=a or b<=j for j in starts)
    save(HERE/"predictions.json.gz",output);save(HERE/"chosen-titles.json.gz",names)
    files=["PROTOCOL_RU.md","NOVELTY_ADDENDUM_RU.md","candidate-receipt.json","panel.json","novelty.json","kernel.json","opening.json",
           "dev-model.json","select_seeds.cpp","panel.py","open_confirm.py","build_native.py","syntax.py","novelty.py","predictions.py",
           "predictions.json.gz","chosen-titles.json.gz"]
    save(HERE/"prediction-seal.json",{"n":len(output),"arms":ARMS,"routes":counts,"local":{k:hashfile(HERE/k) for k in files},
          "cache":{k:hashfile(S/k) for k in ("questions.in","questions.json.gz","seed.tsv","second.in","second.tsv","policy52-direct.tsv","opened.json.gz")},
          "dev_seal":hashfile(GP/"prediction-seal.json")})
    print("SEALED",len(output),dict(counts),hashfile(HERE/"prediction-seal.json"))

if __name__=="__main__":main()

