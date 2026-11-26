"""Independent offline audit of paired token budgets, new outputs, SQL, contrasts and timings."""
import collections
import math
from pathlib import Path
import numpy as np
from scipy.stats import binomtest
from study import HERE,SOURCE,raw,digest
from verify import close,score
import hashlib
import struct

def token_hash(tokens):
    return hashlib.sha256(struct.pack(f"<{len(tokens)}I", *tokens)).hexdigest()
from sql_check import main as check_sql


def check_matching(name,path,choices,old_ctx,old_prompts,old_answers,news,new_prompts,ctx,gold,records,
                   result,metrics,confirmation=False):
    n=len(ctx)
    ids=sorted(ctx)
    assert n==len(choices)==len(gold)==len(records)==len(old_ctx)
    tail=raw(path/"reader-boundaries.json")["tail"]
    pool=dict(old_prompts)
    for k,v in new_prompts.items():
        assert k==token_hash(v) and k not in old_prompts
        pool[k]=v
    answer={**old_answers,**news}
    if confirmation:
        assert set(new_prompts)==set(news)
    clusters={}
    shortened={}
    for q in ids:
        v=ctx[q]
        old=old_ctx[q]
        assert old["cluster"]==v["cluster"] and v["cluster"] not in clusters
        clusters[v["cluster"]]=q
        cap=v["cap"] if confirmation else v["n"]
        assert 0<cap<=old["n"] and old["n"]==(v["original"] if confirmation else v["original_n"])
        if cap<old["n"]:shortened[q]=[old["n"],cap]
        base=old_prompts[old["refs"]["dense"][1]]
        prefix=base[:len(base)-old["n"]-len(tail)]
        assert v["prefix"]==token_hash(prefix)
        assert (v["suffix"] if confirmation else v["tail"])==token_hash(tail)
        old_by_target={i:k for i,k,L in old["refs"].values()}
        for mode,(i,k,L) in v["refs"].items():
            assert i==choices[q][mode] and old["seed"]!=i
            ts=pool[k];assert len(ts)==L==len(prefix)+cap+len(tail)
            assert ts[:len(prefix)]==prefix and ts[-len(tail):]==tail and token_hash(ts)==k
            if i in old_by_target:
                orig=old_prompts[old_by_target[i]]
                assert prefix+orig[len(prefix):len(prefix)+cap]+tail==ts
            if name=="hotpot" or confirmation:
                g=gold[q];labels=[g["answer"]];titles=g["titles"];sup=set(g["support_titles"])
            else:
                labels,titles,ref=gold[q];sup=set(ref)
            x=records[q][mode]
            hits={titles[i],titles[old["seed"]]}&sup
            em,f1=score(answer[k]["answer"],labels)
            assert x["em"]==em and x["full"]==int(hits==sup)
            close(x["f1"],f1);close(x["recall"],len(hits)/len(sup))
            if not confirmation:
                assert x["new"]==(k in news)
    assert result["shortened"]==shortened
    for a,summary in result["policies"].items():
        for k in metrics:
            close(summary[k],math.fsum(records[q][a][k] for q in ids)/n)
        ch=sum(choices[q][a]!=choices[q]["dense"] for q in ids)
        assert summary["changed" if confirmation else "changed_address"]==ch
    cols=[]; intervals=[]
    for pair,stats in result["contrasts"].items():
        a,b=pair.split("-")
        for k,summary in stats.items():
            v=np.array([records[q][a][k]-records[q][b][k] for q in ids])
            pos=int((v>1e-12).sum());neg=int((v< -1e-12).sum())
            assert pos==summary["gains"] and neg==summary["losses"]
            close(100*v.mean(),summary["delta_pp"])
            if "exact_mcnemar" in summary:
                close(summary["exact_mcnemar"],binomtest(pos,pos+neg).pvalue if pos+neg else 1.)
            if "sign_flip" in summary:
                f=summary["sign_flip"]; d=np.abs(v[np.abs(v)>1e-12]);obs=abs(v.sum())
                close(obs,f["observed_abs_sum"]);assert len(d)==f["nonzero"]
                if len(d)>20:
                    rng=np.random.default_rng(510272);extreme=0
                    for _ in range(1000):
                        signs=rng.integers(0,2,size=(1000,len(d)),dtype=np.int8)*2-1
                        extreme+=int((np.abs((signs*d).sum(1))>=obs-1e-12).sum())
                    assert f["extreme"]==extreme and f["draws"]==1000000
                    close((extreme+1)/1000001,f["two_sided_p"])
                else:
                    z=[0.]
                    for weight in d:z=[s-weight for s in z]+[s+weight for s in z]
                    e=sum(abs(s)>=obs-1e-12 for s in z)
                    assert f["draws"]==len(z) and f["extreme"]==e
                    close(e/len(z),f["two_sided_p"])
            cols.append(v); intervals.append(summary["ci95_pp"])
    g=np.stack(cols,axis=1)
    rng=np.random.default_rng(510271)
    boot=np.vstack([g[rng.integers(n,size=(50,n))].mean(1) for _ in range(200)])*100
    assert np.allclose(np.quantile(boot,[.025,.975],axis=0).T,intervals,atol=1e-9)
    return set(clusters)


def check_time():
    data=raw(HERE/"sql-timings.json.gz")
    info=raw(HERE/"sql-cost.json")
    arr=np.asarray([v for _,v in sorted(data.items())])
    assert tuple(arr.shape)==(info["n_queries"],info["repetitions"],3)
    assert info["n_timed"]==arr.size and (arr>0).all()
    for i,name in enumerate(["DENSE","GRAPH","INDEXED_GRAPH"]):
        close(arr[:,:,i].mean()/1000,info["mean_us"][name])
        close(np.median(arr[:,:,i])/1000,info["median_us"][name])
    diff=(arr[:,:,1].astype(float)-arr[:,:,2]).mean(axis=1)
    direct=diff.mean()
    close(direct/1000,info["saving_per_read_us"])
    generator=np.random.default_rng(info["seed"]+1)
    boot=np.hstack([diff[generator.integers(len(diff),size=(50,len(diff)))].mean(axis=1)
                    for _ in range(200)])/1000
    assert np.allclose(np.quantile(boot,[.025,.975]),info["ci95_saving_us"])
    assert info["amortization_read_count"]==math.ceil(np.mean(info["index_build_ns"])/direct)
    assert info["extra_bytes"]==info["database_bytes_after"]-info["database_bytes_before"]
    if info["dbstat"] is not None:
        assert dict(info["dbstat"])["graph_score"]==info["extra_bytes"]


def main():
    sql_result=check_sql()
    ctx=raw(HERE/"matched-contexts.json.gz");dec=raw(HERE/"decisions.json.gz")
    dec["hotpot"]=raw(HERE/"hotpot-decisions.json.gz")
    seal=raw(HERE/"completion-answer-seal.json")
    check=raw(HERE/"reader-replay.json");new=raw(HERE/"new-answers.json.gz");prompts=raw(HERE/"new-prompts.json.gz")
    assert len(new)==len(prompts)==seal["n_new"] and set(new)==set(prompts)
    assert digest(HERE/"reader-replay.json")==seal["replay"]
    assert sum(map(len,check.values()))==36
    covers=set()
    records=raw(HERE/"complete-records.json.gz");results=raw(HERE/"complete-results.json")
    assert raw(HERE/"scoring-receipt.json")["records"]==digest(HERE/"complete-records.json.gz")
    assert raw(HERE/"scoring-receipt.json")["results"]==digest(HERE/"complete-results.json")
    for p,sample in ctx.items():
        root=SOURCE/p if p!="hotpot" else HERE.parent/"transfer"
        old_ctx,oldp,olda,gold=[raw(root/s) for s in ("contexts.json.gz","prompts.json.gz","answers.json.gz","gold.json.gz")]
        for k,c in check[p].items(): assert olda[k]==c["expected"]==c["observed"]
        needed={k for c in sample.values() for i,k,n in c["refs"].values() if k not in oldp}
        assert len(needed)==results[p]["new_unique"] and not needed&covers
        covers.update(needed)
        check_matching(p,root,dec[p],old_ctx,oldp,olda,new,{k:prompts[k] for k in needed},sample,gold,records[p],results[p],
                       ["full","recall","f1","em"])
    assert covers==set(new)
    check_time()
    print("Verified 20,480 scored policy assignments, all 174 new prompts, 36 drift controls, SQL costs and bootstrap contrasts.")


if __name__=="__main__":
    main()
