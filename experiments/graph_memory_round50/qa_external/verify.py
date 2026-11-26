"""Offline numerical audit with the standard library. No archive, model, GPU or previous rounds."""
from collections import Counter
import gzip,hashlib,json,math,re,string,struct
from pathlib import Path
D=Path(__file__).resolve().parent
def get(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(s):
    return re.sub(r"\b(a|an|the)\b"," ","".join(c for c in s.lower() if c not in string.punctuation)).split()
def score(a,ref):
    x=clean(a);result=[0,0.]
    for v in ref:
        y=clean(v);eq=x==y
        blocked=not eq and (" ".join(x) in {"yes","no","noanswer"} or " ".join(y) in {"yes","no","noanswer"})
        n=sum((Counter(x)&Counter(y)).values())
        f=0. if blocked or not n else 2*n/(len(x)+len(y))
        result=[max(result[0],int(eq)),max(result[1],f)]
    return result
def main():
    if (D/"manifest.json").exists():
        for path,h in get(D/"manifest.json")["files"].items():assert digest(D/path)==h,path
    read=lambda n:get(D/n)
    panel=read("panel.json")["order"];orders=read("orders.json.gz");ctx=read("contexts.json.gz")
    inputs=read("prompts.json.gz");answers=read("answers.json.gz");gold=read("gold.json.gz");res=read("outcomes.json.gz")
    rs=read("results.json");seal=read("answer-seal.json")
    assert len(set(panel))==len(panel)==960 and set(panel)==set(orders)==set(ctx)==set(res)==set(gold)
    assert read("input-seal.json")["prompts"]==digest(D/"prompts.json.gz") and seal["answers"]==digest(D/"answers.json.gz")
    assert set(inputs)==set(answers)=={v[1] for c in ctx.values() for v in c["refs"].values()}
    assert all(hashlib.sha256(struct.pack("<"+"I"*len(v),*v)).hexdigest()==k for k,v in inputs.items())
    n=0
    for q,r in orders.items():
        ranked=r["order"];real=r["edges"];leader=r["lex"];true=r["true"]
        assert leader==ranked[0] and true==next((i for i in ranked if str(i) in real),leader)
        targets={"true":true,"lex":leader};record=ctx[q]
        for seed,item in r["sham"].items():
            assert set(item["owners"])==set(real) and {str(j):real[i] for i,j in item["owners"].items()}==item["edges"]
            dest=next((j for j in ranked if str(j) in item["edges"]),leader)
            assert dest==item["second"] and (dest==leader)==(true==leader)
            targets["sham"+seed]=dest
        ref,docs,marked=gold[q]
        assert len(targets)==7 and len({v[2] for v in record["refs"].values()})==1
        for arm,(j,k,L) in record["refs"].items():
            assert j==targets[arm] and len(inputs[k])==L
            a,b=score(answers[k]["answer"],ref);s=res[q]["arms"][arm]
            assert a==s[0] and math.isclose(b,s[1],abs_tol=1e-12)
            used={docs[r["seed"]],docs[j]};marked_set=set(marked);assert s[2]==(marked_set<=used) and s[4]==len(used&marked_set)/len(marked_set)
            n+=1
    assert n==6720
    for group,rows in [("all",list(res.values())),("switched",[v for v in res.values() if v["switch"]]),("same",[v for v in res.values() if not v["switch"]])]:
        g=rs["groups"][group];assert len(rows)==g["n"]
        for pair,info in g["contrasts"].items():
            a,b=pair.split("-")
            def value(v,method,j):
                if method=="sham":return sum(scores[j] for arm,scores in v["arms"].items() if arm.startswith("sham"))/5
                return v["arms"][method][j]
            for j in range(4):
                delta=[value(v,a,j)-value(v,b,j) for v in rows]
                assert abs(sum(delta)/len(delta)*100-info["pp"][j])<1e-9
                assert info["wins"][j]==sum(x>1e-12 for x in delta) and info["losses"][j]==sum(x< -1e-12 for x in delta)
    audit=read("replay.json");assert len(audit)==32 and sum(v!=answers[k] for k,v in audit.items())==seal["different"]
    print("Verified",n,"paired assignments, all question-level official-equivalent EM/F1 and document support scores.")
if __name__=="__main__":main()
