"""Cluster summaries and strict checks over frozen isolated runs."""
from collections import defaultdict
import numpy as np
from bench import D,LOGIT,PAR,read,save,sha,initialise,MATRIX

def main():
    p,_,_=initialise();parent=read(PAR/"build-rows.json.gz");full=read(PAR/"results.json")
    rows=defaultdict(list);process=defaultdict(list);digests={};matched=0;secondary=0
    for rep,m,k in p["runs"]:
        r=read(D/"runs"/f"k{k}-{m}-r{rep}.json.gz");assert r["plan"]==sha(D/"plan.json")
        process[k,m].append([r["peak_wset"],r["increment_over_initial_wset"],r["increment_over_prior_peak"]])
        for q,v in r["rows"].items():
            if (k,q) in digests:assert digests[k,q]==v["digest"]
            else:digests[k,q]=v["digest"]
            rows[k,m,q].append(v);matched+=int(k==30);secondary+=int(k!=30)
    assert matched==1152 and secondary==64
    result={}
    for k in (8,30,120):
        ids=p["ids"] if k==30 else p["stress"]
        meth={}
        for m in MATRIX:
            times=np.array([np.median([z["ns"] for z in rows[k,m,q]])/1e6 for q in ids])
            inputs=np.array([np.median([z["input_ns"] for z in rows[k,m,q]])/1e6 for q in ids])
            pm=np.asarray(process[k,m],dtype=np.float64)/1048576
            meth[m]={"p50_ms":float(np.median(times)),"p95_ms":float(np.percentile(times,95)),"sum_per_query_medians_ms":float(np.sum(times)),
                     "input_p50_ms":float(np.median(inputs)),"peak_working_set_MiB":pm[:,0].tolist(),"peak_increment_MiB":pm[:,1].tolist(),
                     "new_highwater_MiB":pm[:,2].tolist()}
        result[str(k)]=meth
    qids=p["ids"];articles=sorted(set(parent[q]["article"] for q in qids))
    groups=[[i for i,q in enumerate(qids) if parent[q]["article"]==t] for t in articles]
    rng=np.random.default_rng(29041)
    mat=np.array([[np.median([v["ns"] for v in rows[30,m,q]])/1e6 for m in MATRIX] for q in qids])
    contrasts={}
    for test,base in (("dyadic","stream"),("endpoint_matrix","stream"),("dyadic","full_sort"),("endpoint_matrix","full_sort"),("stream","full_sort")):
        j=MATRIX.index(test);l=MATRIX.index(base)
        def summary(x):
            return float(np.median(x[:,j]-x[:,l])),float(np.median(x[:,j])/np.median(x[:,l]))
        boot=[summary(mat[np.concatenate([groups[i] for i in ix])]) for ix in rng.integers(len(articles),size=(10000,len(articles)))]
        v=summary(mat);ci=np.percentile(boot,[2.5,97.5],axis=0).T.tolist()
        contrasts[test+"_vs_"+base]={"diff_ms":v[0],"ratio":v[1],"diff_ci":ci[0],"ratio_ci":ci[1]}
    first=[rows[30,"stream",q][0] for q in qids]
    save(D/"results.json",{"plan":sha(D/"plan.json"),"runs":{path.name:sha(path) for path in sorted((D/"runs").glob("k*.json.gz"))},
        "n":len(qids),"articles":len(articles),"original_candidate_spans":full["db"]["full"]["standalone_entries"],
        "records":sum(v["records"] for v in first),"tokens":sum(v["tokens"] for v in first),
        "complete_parity_comparisons":matched,"stress_parity":secondary,"per_width":result,"intervals":contrasts})
    print(result["30"]);print(contrasts)
if __name__=="__main__":main()
