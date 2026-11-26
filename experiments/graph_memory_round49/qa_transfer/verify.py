"""Standard-library verification, independent of the current grader and model process."""
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,math,re,string,struct

D=Path(__file__).resolve().parent
def get(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def normalize(s):
    text="".join(c for c in s.lower() if c not in string.punctuation)
    return re.sub(r"\b(a|an|the)\b"," ",text).split()
def score(answer,refs):
    x=normalize(answer);best_em=0;best_f=0
    for item in refs:
        y=normalize(item);overlap=sum((Counter(x)&Counter(y)).values())
        best_em=max(best_em,int(x==y));best_f=max(best_f,2*overlap/(len(x)+len(y)) if x or y else 1.)
    return best_em,best_f
def close(a,b):return math.isclose(a,b,rel_tol=0,abs_tol=1e-10)

def main():
    if (D/"manifest.json").exists():
        for n,s in get(D/"manifest.json")["files"].items():assert sha(D/n)==s,n
    reg=get(D/"registration.json");assert reg["protocol"]==sha(D/"PROTOCOL_RU.md")
    raw=get(D/"source-seal.json")
    assert raw["splits"]["dev"]["identical_bytes"] and raw["splits"]["train"]["identical_bytes"]
    orders=get(D/"orders.json.gz");ctx=get(D/"contexts.json.gz");p=get(D/"prompts.json.gz");o=get(D/"answers.json.gz")
    rows=get(D/"outcomes.json.gz");gold=get(D/"gold.json.gz");report=get(D/"results.json")
    assert len(orders)==2417 and set(orders)==set(ctx)==set(rows)==set(gold)
    assert set(p)==set(o)=={v[1] for r in ctx.values() for v in r["refs"].values()}
    assert get(D/"answer-seal.json")["answers"]==sha(D/"answers.json.gz")
    for k,seq in p.items():assert hashlib.sha256(struct.pack(f"<{len(seq)}I",*seq)).hexdigest()==k
    rep=get(D/"replay.json");assert len(rep)==32 and sum(o[k]!=v for k,v in rep.items())==get(D/"answer-seal.json")["different"]
    arms=("true","lex","sham47011","sham47023","sham47039","sham47051","sham47063")
    checks=0
    for q,r in orders.items():
        c=ctx[q];g=rows[q];marked=r["edges"];order=r["order"]
        assert r["true"]==next((i for i in order if str(i) in marked),order[0]) and r["lex"]==order[0]
        target={"true":r["true"],"lex":r["lex"]}
        for s,sham in r["sham"].items():
            owners=sham["owners"];assert set(owners)==set(marked)
            assert {str(j):marked[i] for i,j in owners.items()}==sham["edges"]
            x=next((i for i in order if str(i) in sham["edges"]),order[0])
            assert x==sham["second"] and (x==order[0])==(r["true"]==order[0])
            target["sham"+s]=x
        assert set(c["refs"])==set(arms) and len({v[2] for v in c["refs"].values()})==1
        ref,ids=gold[q]
        for arm,(idx,k,n) in c["refs"].items():
            assert target[arm]==idx and n==len(p[k])
            em,f=score(o[k]["answer"],ref);stored=g["arms"][arm]
            assert close(em,stored[0]) and close(f,stored[1]) and stored[2]==(set(ids)<={idx,r["seed"]})
            checks+=1
    assert checks==2417*7
    for name,sel in [("all",list(rows.values())),("switched",[r for r in rows.values() if r["switch"]]),
                     ("unchanged",[r for r in rows.values() if not r["switch"]])]:
        for pair,info in report["groups"][name]["contrasts"].items():
            a,b=pair.split("-")
            for metric in range(4):
                def value(row,arm):
                    if arm=="sham":return sum(row["arms"][s][metric] for s in arms[2:])/5
                    return row["arms"][arm][metric]
                deltas=[value(row,a)-value(row,b) for row in sel]
                assert close(100*sum(deltas)/len(deltas),info["pp"][metric])
                assert sum(z>1e-12 for z in deltas)==info["wins"][metric] and sum(z< -1e-12 for z in deltas)==info["losses"][metric]
    print("PASS",len(p),"prompt byte identities,",checks,"official-equivalent EM/F1 outcomes and paired contrasts.")
if __name__=="__main__":main()
