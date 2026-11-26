"""Test sensitivity of case resampling to duplicated questions/state pairs in the synthetic collection."""
import collections,itertools
from base31 import D,P,h,sha,read,save,DATA,data,Path
from score31 import tokenize,join_source
def normalized(s):return " ".join(t[0] for t in tokenize(s))
def main():
    import numpy as np
    qs=data();rows=read(D/"score-rows.json.gz");lookup=read(D/"case-split.json");lab=read(DATA/"evaluator/labels.json.gz")
    shares=collections.defaultdict(set);bodies=collections.defaultdict(set);unique_side=collections.defaultdict(set);factpairs={};cases=list(qs)
    corp=collections.Counter();datasets=collections.defaultdict(set);all_grams={}
    for c,qq in qs.items():
        normq=sorted(normalized(s) for s in qq.values())
        for s in normq:shares[h(s)].add(c)
        combined=" ".join(normq).split();all_grams[c]={" ".join(combined[j:j+5]) for j in range(max(1,len(combined)-4))}
        for z in read(DATA/"history"/(c+".json.gz"))["sources"]:
            doc=h(join_source(z)[0]);corp[doc]+=1;datasets[doc].add(c)
    for z in lab:
        c=z["case"];pair=tuple(normalized(z[k]) for k in ("old","new"));bodies[pair].add(c);factpairs[c]=pair
        for k,s in zip(("old","new"),pair):unique_side[k,h(s)].add(c)
    parent={c:c for c in cases}
    def find(c):
        while parent[c]!=c:parent[c]=parent[parent[c]];c=parent[c]
        return c
    def union(a,b):
        a=find(a);b=find(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    for coll in (shares,bodies):
        for vals in coll.values():
            a,*others=sorted(vals)
            for b in others:union(a,b)
    similar=0
    for a,b in itertools.combinations(cases,2):
        g=all_grams[a];v=all_grams[b];j=len(g&v)/max(1,len(g|v))
        if j>=.90:similar+=1;union(a,b)
    comps=collections.defaultdict(set)
    for c in cases:comps[find(c)].add(c)
    test={c for c,v in lookup.items() if v=="test"}
    ha={c:find(c) for c in test};groups=sorted({ha[c] for c in test});agg={}
    for base in ("win_hybrid","turn_ensemble","first","last"):
        by=collections.defaultdict(dict)
        for z in rows:
            if z["method"] in (base,"turn_pair") and z["split"]=="test" and z["scope"]=="known":
                by[z["case"],z["q"]][z["method"]]=z["both_full"]
        dif=collections.Counter();n=collections.Counter()
        for (c,q),g in by.items():dif[ha[c]]+=int(g["turn_pair"])-int(g[base]);n[ha[c]]+=1
        vals=np.array([dif[k] for k in groups]);ns=np.array([n[k] for k in groups]);ii=np.random.default_rng(310258).integers(0,len(groups),(10000,len(groups)),dtype=np.int16)
        effect=vals[ii].sum(axis=1)/ns[ii].sum(axis=1);agg[base]={"delta":float(vals.sum()/ns.sum()),"cluster_975":np.quantile(effect,[.0125,.9875]).tolist()}
    result={"score":sha(D/"score.json"),"code":sha(Path(__file__)),"cases":len(cases),"test_cases":len(test),"distinct_normalized_questions":len(shares),
          "n_questions_repeated_across_cases":sum(len(v)>1 for v in shares.values()),"distinct_normalized_fact_pairs":len(bodies),
          "n_fact_pairs_repeated_across_cases":sum(len(v)>1 for v in bodies.values()),"n_near_triple_pairs":similar,
          "all_components":len(comps),"test_components":len(groups),"test_cases_linked_to_dev":sum(any(lookup[other]=="dev" for other in comps[ha[c]]) for c in test),
          "largest_all_component":max(map(len,comps.values())),"distinct_session_bodies":len(corp),"n_session_rows":sum(corp.values()),
          "number_session_bodies_shared_across_cases":sum(len(a)>1 for a in datasets.values()),"max_cases_sharing_a_body":max(map(len,datasets.values())),
          "test_contrasts":agg,"component_by_case":{c:find(c) for c in cases}}
    save(D/"reuse-audit.json",result)
if __name__=="__main__":main()
