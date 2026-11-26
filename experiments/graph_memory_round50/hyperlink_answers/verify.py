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
    import statistics
    read=lambda n:get(D/n)
    if (D/"manifest.json").exists():
        for n,h in read("manifest.json")["files"].items():assert digest(D/n)==h,n
    ranks=read("orders.json.gz");ctx=read("contexts.json.gz");out=read("answers.json.gz");inp=read("prompts.json.gz")
    labels=read("gold.json.gz");rows=read("outcomes.json.gz");reuse=read("reuse.json.gz");lock=read("answer-seal.json");ir=read("input-seal.json")
    assert ir["prompts"]==digest(D/"prompts.json.gz") and lock["answers"]==digest(D/"answers.json.gz") and len(reuse)==lock["cached"]
    assert set(out)==set(inp)=={v[1] for r in ctx.values() for v in r["refs"].values()} and set(ctx)==set(ranks)==set(labels)==set(rows)
    assert len(inp)-len(reuse)==lock["new"]
    for k,ts in inp.items():assert hashlib.sha256(struct.pack("<"+"I"*len(ts),*ts)).hexdigest()==k
    tail=ir["tail"];total=0
    for q,r in ranks.items():
        v=ctx[q];assert all(i!=r["seed"] for i in r["order"])
        marks=set(r["text_edges"]);href=set(r["href_edges"])
        pick=lambda edges:next((i for i in r["order"] if i in edges),r["order"][0])
        assert [r["true"],r["href"],r["union"]]==[pick(marks),pick(href),pick(marks|href)]
        assert len(v["refs"])==3 and len({a[2] for a in v["refs"].values()})==1 and v["n"]<=v["old_n"]
        ps=[inp[a[1]] for a in v["refs"].values()];j=len(ps[0])-v["n"]-len(tail)
        assert all(t[:j]==ps[0][:j] and t[-len(tail):]==tail for t in ps)
        truth,titles,support=labels[q];sp=set(support)
        for a,(i,k,n) in v["refs"].items():
            assert i==r[a] and len(inp[k])==n
            em,f1=score(out[k]["answer"],truth);used={titles[i],titles[r["seed"]]};s=rows[q]["arms"][a]
            assert em==s[0] and abs(f1-s[1])<1e-12 and int(sp<=used)==s[2] and len(used&sp)/len(sp)==s[3];total+=1
    for split,g in read("results.json").items():
        items=[r for r in rows.values() if r["split"]==split];assert len(items)==g["n"]
        for pair,c in g["contrasts"].items():
            x,y=pair.split("-")
            for j in range(4):
                ds=[i["arms"][x][j]-i["arms"][y][j] for i in items]
                assert abs(100*statistics.mean(ds)-c["pp"][j])<1e-9
                assert [sum(d>1e-12 for d in ds),sum(d< -1e-12 for d in ds)]==[c["wins"][j],c["losses"][j]]
    audit=read("replay.json");expected=set()
    for group in [set(reuse),set(inp)-set(reuse)]:
        expected.update(sorted(group,key=lambda k:hashlib.sha256(("r50-href-repeat|"+k).encode()).hexdigest())[:32])
    assert set(audit)==expected and sum(v!=out[k] for k,v in audit.items())==lock["different"]
    print("Verified",total,"paired assignments, answer/support scores, both panels, full-input identities and both replay strata.")
if __name__=="__main__":main()

