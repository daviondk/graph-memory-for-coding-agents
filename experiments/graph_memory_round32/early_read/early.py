"""Lossless stopping for mention-priority retrieval, tested against sealed full reads."""
from collections import Counter
from pathlib import Path
import sys,re,json,math
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"observed_transfer"))
sys.path.insert(0,str(HERE.parent/"musique_links"))
from transfer import SRC, get,put,sha,pq,json,catalog,ranks,words,E5,Tokenizer,tie
from run_musique import data
def cases(name):
    if name=="2wiki":
        for batch in pq.ParquetFile(SRC).iter_batches(columns=["_id","question","context"],batch_size=256):
            for r in batch.to_pylist():
                q=r["_id"];ps=json.loads(r["context"]);idx=sorted(range(len(ps)),key=lambda i:tie(q+"|"+ps[i][0]))
                yield q,r["question"],[ps[i][0] for i in idx],[ps[i][1] for i in idx],list(range(len(ps)))
    else:
        for r in data():
            q=r["id"];ps=r["paragraphs"];idx=sorted(range(len(ps)),key=lambda i:tie(q+"|musique|"+str(ps[i]["idx"])))
            yield q,r["question"],[ps[i]["title"] for i in idx],[[ps[i]["paragraph_text"]] for i in idx],[ps[i]["idx"] for i in idx]
def actions(query,titles,docs,tok):
    seq,_,bm=catalog(query,titles);sort=ranks(bm(query));prior=sorted(sort,key=sort.get);seed,best=prior[:2]
    raw=" ".join(docs[seed]);offsets=tok.encode(raw,add_special_tokens=False).offsets[:192];limit=len(offsets)
    keys={j:" "+" ".join(seq[j])+" " for j in prior[1:] if seq[j] and sum(map(len,seq[j]))>=3}
    full_words={}
    def evaluate(k):
        if k not in full_words:
            snippet=raw[:offsets[k-1][1]] if k else ""
            if k<limit:snippet=re.sub(r"[^\W_]+$","",snippet,flags=re.UNICODE)
            text=" "+" ".join(words(snippet))+" "
            j=next((i for i in prior[1:] if i in keys and keys[i] in text),None)
            full_words[k]=(j if j is not None else best,j==best)
        return full_words[k]
    out={"full":[evaluate(limit)[0],limit,1]}
    for step in (16,32,64):
        k=min(step,limit);calls=1
        while k<limit and not evaluate(k)[1]:
            k=min(k+step,limit);calls+=1
        out["cert"+str(step)]=[evaluate(k)[0],k,calls]
    for cap in (32,64,96):
        k=min(cap,limit);out["fixed"+str(cap)]=[evaluate(k)[0],k,1]
    return seed,out
def main():
    tok=Tokenizer.from_file(str(E5/"tokenizer.json"))
    folders={"2wiki":"observed_transfer","musique":"musique_links"}
    fingerprints={n:sha(HERE.parent/f/"predictions.json.gz") for n,f in folders.items()}
    put(HERE/"plan.json",{"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),"predictions":fingerprints,"tokenizer":sha(E5/"tokenizer.json")})
    detailed={};summary={}
    for name,folder in folders.items():
        ref=get(HERE.parent/folder/"predictions.json.gz");records={}
        for q,question,titles,docs,ids in cases(name):
            seed,row=actions(question,titles,docs,tok);prior=ref[q]
            assert ids[seed]==prior["seed"] and ids[row["full"][0]]==prior["next"]["mention_title"] and row["full"][1]==prior["tokens"],(name,q)
            assert all(v[0]==row["full"][0] for k,v in row.items() if k.startswith("cert")),(name,q,row)
            records[q]={m:[ids[v[0]],v[1],v[2]] for m,v in row.items()}
        assert set(records)==set(ref)
        detailed[name]=records
    put(HERE/"actions.json.gz",detailed);put(HERE/"seal.json",{"actions":sha(HERE/"actions.json.gz"),"plan":sha(HERE/"plan.json")})
    for name,folder in folders.items():
        ref=get(HERE.parent/folder/"predictions.json.gz");records=detailed[name];gold={}
        if name=="2wiki":
            for batch in pq.ParquetFile(SRC).iter_batches(columns=["_id","context","supporting_facts"]):
                for r in batch.to_pylist():
                    q=r["_id"];p=json.loads(r["context"]);g={t for t,_ in json.loads(r["supporting_facts"])}
                    ts=[p[i][0] for i in ref[q]["order"]]
                    gold[q]=(len(g),ts,g)
        else:
            for r in data():
                inds=[p["idx"] for p in r["paragraphs"] if p["is_supporting"]];gold[r["id"]]=(len(inds),None,set(inds))
        scores={}
        for m in next(iter(records.values())):
            cnt=Counter()
            for q,r in records.items():
                j,k,c=r[m];cnt.update({"tokens":k,"blocks":c,"identical":int(j==r["full"][0]),"early":int(k<r["full"][1])})
                n,ts,g=gold[q];s=ref[q]["seed"]
                if n==2:
                    cnt["n_two"]+=1;cnt["both"]+=int(({ts[j],ts[s]} if ts is not None else {j,s})==g)
            scores[m]={**cnt,"mean_tokens":cnt["tokens"]/len(records),"mean_blocks":cnt["blocks"]/len(records)}
        summary[name]={"n":len(records),"scores":scores}
    put(HERE/"results.json",summary)
if __name__=="__main__":main()
