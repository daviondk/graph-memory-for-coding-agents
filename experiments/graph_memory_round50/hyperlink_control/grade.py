"""Evaluate after freezing both forecasts, using the previously audited official support-title hashes."""
import os
for opt in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[opt]="1"
from collections import Counter
import numpy as np
from common import *
ARMS=("text","lex","href","direct","literal","union")

def calculate(rows,truth):
    qs=sorted(rows);cluster,ix=np.unique([rows[q]["cluster"] for q in qs],return_inverse=True)
    values=[];counts=Counter();edge=Counter();by_source=Counter();groups={}
    for q in qs:
        r=rows[q];titles,gids=truth[q];gold=set(gids)
        vals=[]
        for name in ARMS:
            sel={titles[r["seed"]],titles[r["choices"][name]]}
            vals.append([float(gold<=sel),len(gold&sel)/len(gold)])
        values.append(vals);counts[r["status"]]+=1
        by_source.update({k:int(r[k]) for k in ("full_whitespace","full_literal","prefix_literal")})
        te,he=set(r["text_edges"]),set(r["href_edges"])
        edge.update({"text_edges":len(te),"href_edges":len(he),"overlap_edges":len(te&he),"text_any":bool(te),"href_any":bool(he),
                     "href_only_edges":len(he-te),"text_only_edges":len(te-he),"any_recovered_by_id":bool(he-set(r["direct_edges"])),
                     "choices_agree":r["choices"]["text"]==r["choices"]["href"],"href_vs_lex_switch":r["choices"]["href"]!=r["choices"]["lex"],
                     "text_vs_lex_switch":r["choices"]["text"]!=r["choices"]["lex"],"gold_reachable_href":any(titles[i] in gold and titles[i]!=titles[r["seed"]] for i in he),
                     "gold_reachable_text":any(titles[i] in gold and titles[i]!=titles[r["seed"]] for i in te)})
    a=np.array(values)
    counts_cl=np.bincount(ix)
    agg=np.zeros((len(cluster),len(ARMS),2));np.add.at(agg,ix,a)
    rng=np.random.default_rng(503410);boots=[]
    for _ in range(100):
        t=rng.integers(len(cluster),size=(100,len(cluster)))
        weights=np.stack([np.bincount(z,minlength=len(cluster)) for z in t])
        boots.append((weights@agg.reshape(len(cluster),-1)).reshape((-1,len(ARMS),2))/(weights@counts_cl)[:,None,None])
    bs=np.concatenate(boots,axis=0)
    comps={}
    for lhs,rhs in (("href","text"),("href","lex"),("text","lex"),("direct","href"),("literal","href"),("union","text")):
        i,j=ARMS.index(lhs),ARMS.index(rhs);de=a[:,i]-a[:,j]
        comps[lhs+"-"+rhs]={"delta":de.mean(axis=0).tolist(),"ci":np.quantile(bs[:,i]-bs[:,j],[.025,.975],axis=0).T.tolist(),"wins":int((de[:,0]>0).sum()),"losses":int((de[:,0]<0).sum())}
    for k,predicate in {"verified_visible":lambda r:r["status"]=="ok","fully_equal_without_spaces":lambda r:r["full_whitespace"],"linked":lambda r:bool(r["href_edges"]),"different_choice":lambda r:r["choices"]["href"]!=r["choices"]["text"]}.items():
        use=np.array([predicate(rows[q]) for q in qs])
        groups[k]={"n":int(use.sum()),"complete":a[use,:,0].sum(axis=0).astype(int).tolist()}
    return {"n":len(qs),"clusters":len(cluster),"status":dict(counts),"identity":dict(by_source),"edges":dict(edge),"arms":list(ARMS),
            "complete":a[:,:,0].sum(axis=0).astype(int).tolist(),"rates":a.mean(axis=0).tolist(),"contrasts":comps,"conditional":groups}

def main():
    seal=read(D/"prediction_seal.json");all_results={}
    for split,study in CONFIG.items():
        path=D/f"forecast-{split}.json.gz"
        assert seal["subsets"][split]["predictions"]==sha(path)
        upstream=D.parent/study
        g=upstream/"gold.json.gz";assert sha(g)==read(upstream/"manifest.json")["files"]["gold.json.gz"]
        raw=read(g);rows=read(path);assert set(rows)==set(raw)
        truths={q:r[1:] for q,r in raw.items()}
        portable=D/f"support-{split}.json.gz";write(portable,truths)
        all_results[split]=calculate(rows,truths)
        all_results[split]["source_gold_sha"]=sha(g)
        print(split,all_results[split]["complete"],all_results[split]["contrasts"]["href-text"],flush=True)
    write(D/"results.json",all_results)
if __name__=="__main__":main()

