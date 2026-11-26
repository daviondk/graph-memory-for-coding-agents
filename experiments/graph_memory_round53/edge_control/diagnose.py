"""Post-selection accounting: which observed wins could any visible literal have recovered?"""
from collections import Counter
from grade import canon
from setup import *
def main(verify=False):
    allpan={}
    names=read(D/"titles.json.gz")
    for p in ("2wiki","hotpot"):
        rows=read(D/(p+"-choices.json.gz"));labels=read(SPLITS[p][0]/("support.json.gz" if p=="2wiki" else "gold.json.gz"))
        stats=Counter();examples={}
        for q,r in rows.items():
            nh,nl,k,_=r["sizes"]
            if r["direct"] or not k:continue
            h,li=r["random"];gs=set(labels[q][1]);seed=canon(names[str(r["seed"])])
            def ok(i):return gs.issubset({seed,canon(names[str(i)])})
            observed=ok(r["fixed"][0]);proxy=ok(r["fixed"][4]);possible_h=any(ok(i) for i in h);possible_l=any(ok(i) for i in li)
            stats["eligible"]+=1;stats["oracle_href"]+=possible_h;stats["oracle_literal"]+=possible_l
            if observed and not proxy:
                k="proxy_win_despite_possible_literal" if possible_l else "proxy_win_no_sufficient_literal"
                stats[k]+=1
                if k not in examples:examples[k]=dict(q=q,seed=seed,selected=names[str(r["fixed"][0])],text_selected=names[str(r["fixed"][4])])
            if proxy and not observed:stats["proxy_loss_with_possible_href" if possible_h else "proxy_loss_no_sufficient_href"]+=1
        allpan[p]=dict(counts=dict(stats),first_id_examples=examples)
    if verify:assert allpan==read(D/"diagnostic.json")
    else:save(D/"diagnostic.json",allpan)
    return allpan
if __name__=="__main__":
    import sys
    print(main("--verify" in sys.argv))
