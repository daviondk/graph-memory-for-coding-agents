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

def verify_flip(sig):
    import itertools
    ds=list(sig["nonzero"].values());weights=list(map(abs,ds));observed=abs(math.fsum(ds))
    assert len(ds)==sig["k"] and abs(sig["observed_abs_sum"]-observed)<1e-12
    if len(ds)<=20:
        sums=[0.]
        for w in weights:sums=[a-w for a in sums]+[a+w for a in sums]
        n=sum(abs(s)>=observed-1e-12 for s in sums)
        assert n==sig["extreme"] and sig["draws"]==len(sums) and n/len(sums)==sig["two_sided_p"]
    else:
        assert sig["method"]=="monte-carlo-plus-one" and sig["draws"]==1000000 and sig["seed"]==500731
        assert (sig["extreme"]+1)/(sig["draws"]+1)==sig["two_sided_p"]
def main():
    import base64
    import statistics
    read=lambda n:get(D/n)
    if (D/"manifest.json").exists():
        for n,s in read("manifest.json")["files"].items():assert digest(D/n)==s,n
    panel=read("panel.json")["order"];orders=read("orders.json.gz");cat=read("catalog-receipts.json.gz")
    ctx=read("contexts.json.gz");gold=read("gold.json.gz");rows=read("outcomes.json.gz")
    inp=read("prompts.json.gz");out=read("answers.json.gz");audit=read("replay.json");res=read("results.json")
    assert len(set(panel))==len(panel)==1280 and all(set(panel)==set(v) for v in [orders,cat,ctx,gold,rows])
    assert len({v["cluster"] for v in ctx.values()})==1280
    assert read("input-seal.json")["prompts"]==digest(D/"prompts.json.gz") and read("answer-seal.json")["answers"]==digest(D/"answers.json.gz")
    assert set(inp)==set(out)=={v[1] for c in ctx.values() for v in c["refs"].values()}
    boundaries=read("reader-boundaries.json");tail=boundaries["tail"]
    for k,ts in inp.items():assert hashlib.sha256(struct.pack("<"+"I"*len(ts),*ts)).hexdigest()==k
    thresh=read("threshold-seal.json");news=read("novelty.json.gz")
    assert read("panel.json")["threshold"]==digest(D/"threshold-seal.json")==read("retrieval-seal.json")["threshold"]
    assert read("input-seal.json")["retrieval"]==digest(D/"retrieval-seal.json")
    assert set(news["new"])==set(panel) and not set(news["historical"])&set(panel)
    for col in (0,1):assert not {v[col] for v in news["historical"].values()}&{v[col] for v in news["new"].values()}
    assert thresh["primary"]==0.04178261756896973 and read("registration.json")["threshold"]==thresh["source"]
    for q,r in orders.items():
        obs=cat[q];s=r["scores"];marks=set(r["edges"]);dense=sorted(obs["tie"],key=lambda i:-s[str(i)])
        assert set(obs["tie"])==set(map(int,s)) and r["seed"]==obs["first"] and r["seed"] not in dense
        assert dense==r["order"] and dense[0]==r["dense"] and 0<=obs["observed"]<=192
        assert next((i for i in dense if i in marks),dense[0])==r["linked_dense"]
        gap=None if r["linked_dense"]==r["dense"] else s[str(r["dense"])]-s[str(r["linked_dense"])]
        assert gap==r["gap"] and news["new"][q][1]==ctx[q]["cluster"]
        for arm,cut in [("adaptive",thresh["primary"])]:
            assert r[arm]==(r["linked_dense"] if gap is not None and cut is not None and gap<=cut else r["dense"])
        assert marks<=set(dense) and set(dense)==set(r["lex_order"]) and r["lex_order"][0]==r["lex"]
        assert next((i for i in r["lex_order"] if i in marks),r["lex"])==r["true"]
        assert len(ctx[q]["refs"])==3 and len({z[2] for z in ctx[q]["refs"].values()})==1
        ps=[inp[z[1]] for z in ctx[q]["refs"].values()];j=len(ps[0])-ctx[q]["n"]-len(tail)
        assert all(t[:j]==ps[0][:j] and t[-len(tail):]==tail for t in ps)
        assert ctx[q]["n"]<=ctx[q]["old_n"] and ctx[q]["switch"]==(r["dense"]!=r["adaptive"])
        truth,titles,support=gold[q];sp=set(support)
        for arm,(i,k,L) in ctx[q]["refs"].items():
            assert i==r[arm] and len(inp[k])==L

            scores=rows[q]["arms"][arm];em,f1=score(out[k]["answer"],truth)
            assert em==scores[0] and math.isclose(f1,scores[1],abs_tol=1e-12)
            selected={titles[r["seed"]],titles[i]}
            assert int(sp<=selected)==scores[2] and scores[4]==len(sp&selected)/len(sp)
    # Standalone FP64 accumulation from the exported float32 vectors, independently of NumPy and BLAS.
    sample=read("vector-check.json.gz");vec={k:struct.unpack("<4096f",base64.b64decode(v)) for k,v in sample["vectors"].items()}
    import hashlib as h
    expected=sorted(panel,key=lambda q:h.sha256(("r50-vector-audit|"+q).encode()).hexdigest())[:8]
    assert set(expected)==set(sample["rows"]);pairs=0
    for q,(query,docs) in sample["rows"].items():
        assert len(docs)==len(orders[q]["scores"])
        for i,k in docs:
            cosine=math.fsum(x*y for x,y in zip(vec[query],vec[k],strict=True))
            assert math.isclose(cosine,orders[q]["scores"][str(i)],abs_tol=1e-6)
            pairs+=1
    for key,g in res["groups"].items():
        gq=[q for q in panel if key=="all" or (key=="switched" and ctx[q]["switch"])
            or (key=="same" and not ctx[q]["switch"]) or key=="type_"+rows[q]["kind"]]
        assert len(gq)==g["n"]
        for pair,result in g["contrasts"].items():
            a,b=pair.split("-")
            for m in range(5):
                delta=[rows[q]["arms"][a][m]-rows[q]["arms"][b][m] for q in gq]
                assert abs(statistics.mean(delta)*100-result["pp"][m])<1e-9
                assert result["wins"][m]==sum(d>1e-12 for d in delta) and result["losses"][m]==sum(d< -1e-12 for d in delta)
    for arm,metrics in res["official"].items():
        for m,k in enumerate(["em","f1"]):
            assert abs(metrics[k]-100*statistics.mean(rows[q]["arms"][arm][m] for q in panel))<=0.005000001
    assert len(audit)==32 and sum(v!=out[k] for k,v in audit.items())==read("answer-seal.json")["different"]
    from fractions import Fraction
    bonus=read("bonus-audit.json.gz")
    for q,r in orders.items():
        marks=set(r["edges"]);vals={int(i):Fraction.from_float(v) for i,v in r["scores"].items()};threshold=Fraction.from_float(thresh["primary"])
        winner=max(cat[q]["tie"],key=lambda i:(vals[i]+(threshold if i in marks else 0),i in marks))
        assert winner==r["adaptive"] and bonus["confirmation"][q][:3]==[winner]*3
    sig=read("signflip-new.json")
    ds={q:r["arms"]["adaptive"][1]-r["arms"]["dense"][1] for q,r in rows.items()}
    assert sig["nonzero"]=={q:d for q,d in ds.items() if d!=0}
    for name in ["new","old"]:verify_flip(read("signflip-"+name+".json"))
    print("Verified 3840 QA and support scores, every rank, cutoff and exact-rational bonus,",pairs,"sampled cosine pairs and both sign-flip decisions.")
if __name__=="__main__":main()
