"""Exhaustive conditional shams with matched rank blocks. Does not run the answer model."""
from pathlib import Path
from itertools import combinations,product
from collections import Counter
from fractions import Fraction
import re,gzip,json,hashlib,os
import numpy as np

D=Path(__file__).resolve().parent
R=D.parent
BASE=R/"baseline"
ROOT=Path(os.environ.get("MEMORY_DATA_ROOT","D:/CodexResearch"))
PANELS=[("2wiki1280",R.parent/"graph_memory_round50/gate_confirmation",ROOT/"x20-r50-gate-confirmation"),
        ("hotpot640",R/"transfer",ROOT/"x20-r51-hotpot-gate"),("hotpot1280",R/"routing",ROOT/"x20-r51-hotpot-routing")]
PLAN="a02985c3154119b10203972d3b47678f463fe368bde2c28323fca1cd489ad476"

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rd(p):
 b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(p,v):
 b=(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
 (D/p).write_bytes(gzip.compress(b,mtime=0) if p.endswith(".gz") else b)

def term_list(s):
 return re.findall(r"[^\W_]+",s.lower())

def exact_shams(raw,bit,good,hybrid_order,block,bonus):
    groups=[hybrid_order[i:i+block] for i in range(0,len(bit),block)]
    configs=[list(combinations(g,sum(bit[j] for j in g))) for g in groups]
    winners=Counter()
    for choices in product(*configs):
        marked={int(j) for opt in choices for j in opt}
        selected=max(range(len(bit)),key=lambda j:raw[j]+bonus*(j in marked))
        winners[selected]+=1
    return {"n":sum(winners.values()),"success":sum(count for j,count in winners.items() if good[j]),"win":dict(winners)}

def summaries(rows):
    output={}
    observed=np.array([r["correct"] for r in rows],int)
    for m in ("pair","triple","unrestricted"):
        p=np.array([s[m]["success"]/s[m]["n"] for s in rows])
        diff=observed-p
        # Exact null under independent conditional draws, no Monte Carlo tail truncation.
        dist=np.array([1.]);certain=int(np.sum(p==1))
        for v in p[(p>0)&(p<1)]: dist=np.convolve(dist,[1-v,v])
        observed_count=int(observed.sum())
        tail=float(dist[max(0,observed_count-certain):].sum())
        rng=np.random.default_rng(512451);boot=[]
        for _ in range(25):
            ids=rng.integers(len(rows),size=(400,len(rows)))
            boot.extend(diff[ids].mean(1))
        output[m]=dict(observed=observed_count,expected=float(p.sum()),delta_pp=100*float(diff.mean()),
          ci_pp=(100*np.quantile(boot,[.025,.975])).tolist(),null_upper_p=min(tail,1.0),movable_winner=sum(len(r[m]["win"])>1 for r in rows),
          support_variable=int(np.count_nonzero((p>0)&(p<1))),draws=sum(r[m]["n"] for r in rows))
    return output

def run(lexical=True):
    assert sha(D/"PROTOCOL_RU.md")==PLAN
    model=rd(BASE/"model.json")
    means=np.asarray(model["mean"]);scales=np.asarray(model["scale"])
    w=np.array(model["graph"]["coef"]);wh=np.array(model["hybrid"]["coef"])
    fixed=float(w[4]/scales[4])
    allrec={};summ={};sources={}
    for name,path,private in PANELS:
        ranks=rd(path/"orders.json.gz");lex=rd(path/"lex-orders.json.gz");gold=rd(path/"gold.json.gz")
        receipts=rd(path/"catalog-receipts.json.gz")
        if name=="2wiki1280": decisions=rd(BASE/"decisions.json.gz")["gate_confirmation"]
        elif name=="hotpot640": decisions=rd(BASE/"hotpot-decisions.json.gz")
        else: decisions=rd(BASE/"confirm/choices.json.gz")
        allrefs=rd(path/"contexts.json.gz")
        assert len({z["cluster"] for z in allrefs.values()})==len(allrefs)
        hashes={p:sha(path/p) for p in ("orders.json.gz","lex-orders.json.gz","gold.json.gz","catalog-receipts.json.gz","contexts.json.gz")}
        if lexical:
            catpath=private/"catalog-input.json.gz";project=rd(path/"projection-seal.json")
            assert sha(catpath)==project["visible"]
            cats=rd(catpath);hashes["catalog-input"]=sha(catpath)
        rows={};npos=0;ndoc=0;nedge=0;nfirst=0;nall=0
        for q,r in sorted(ranks.items()):
            idx=r["order"];l=lex[q];g=gold[q];n=len(idx)
            x=np.array([[r["scores"][str(j)],1/(1+l["question_rank"][str(j)]),1/(1+l["snippet_rank"][str(j)]),1/(1+i)]
                        for i,j in enumerate(idx)])
            std=(x-means[:4])/scales[:4];raw=std@w[:4];hrank=np.argsort(-(std@wh),kind="stable").tolist()
            bit=[int(j in r["edges"]) for j in idx]
            titles_all,support=(g[1],g[2]) if isinstance(g,list) else (g["titles"],g["support_titles"])
            good=[int(set(support)<={titles_all[r["seed"]],titles_all[j]}) for j in idx]
            winner=int(np.argmax(raw+fixed*np.array(bit)))
            assert idx[winner]==decisions[q]["graph"] and idx[hrank[0]]==decisions[q]["hybrid"]
            assert set(r["edges"])==set(map(int,l["edges"]))
            if lexical:
                question,snippet,titles=cats[q]
                assert hashlib.sha256(snippet.encode()).hexdigest()==receipts[q]["snippet"]
                tokens=term_list(snippet);edges={}
                for j,t in titles:
                    assert hashlib.sha256(t.encode()).hexdigest()==receipts[q]["titles"][str(j)]
                    seq=term_list(t);k=len(seq)
                    hits=[a for a in range(len(tokens)-k+1) if tokens[a:a+k]==seq] if sum(map(len,seq))>=3 else []
                    if hits: edges[str(j)]=hits
                assert edges==l["edges"],q
                npos+=sum(map(len,edges.values()));nedge+=len(edges);ndoc+=len(titles)
            row=dict(correct=good[winner],hybrid=good[hrank[0]],common_winner=good[int(np.argmax(raw))],winner=winner,idx=idx,ordered_hybrid=hrank,
                     raw=[float(u) for u in raw],bit=bit,good=good)
            for m,b in [("pair",2),("triple",3),("unrestricted",n)]:
                row[m]=exact_shams(raw,bit,good,hrank,b,fixed)
            nfirst+=int(any(bit));nall+=n;rows[q]=row
        allrec[name]=rows
        summ[name]=dict(n=len(rows),candidate_count=nall,with_edge=nfirst,hybrid_correct=sum(r["hybrid"] for r in rows.values()),
            frozen_without_edge=sum(r["common_winner"] for r in rows.values()),conditions=summaries(list(rows.values())),
            lexical=dict(titles=ndoc,matched=nedge,locations=npos) if lexical else None)
        sources[name]=hashes
    conditions=sorted(summ,key=lambda k:summ[k]["conditions"]["pair"]["null_upper_p"]);running=0.
    for i,k in enumerate(conditions):
        z=summ[k]["conditions"]["pair"]
        running=max(running,min(1.,(len(conditions)-i)*z["null_upper_p"]));z["holm_three"]=running
    return allrec,dict(panels=summ,sources=sources,model=sha(BASE/"model.json"),bonus=fixed,protocol=PLAN)
if __name__=="__main__":
    records,results=run()
    save("records.json.gz",records)
    results["records"]=sha(D/"records.json.gz");save("results.json",results)
    print(json.dumps({k:{m:[round(v["delta_pp"],3),v["ci_pp"],v["null_upper_p"],v["movable_winner"]] for m,v in r["conditions"].items()} for k,r in results["panels"].items()}))

