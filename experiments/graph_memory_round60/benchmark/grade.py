"""Evaluate stored choices. All possible random schedules are counted exactly within repository."""
from collections import Counter, defaultdict
import math
import random
import statistics
from common import HERE, load, save, sha

def mcnemar(w,l):
    return min(1.,2*sum(math.comb(w+l,k) for k in range(min(w,l)+1))/2**(w+l))

def contrast(records,a,b):
    groups=defaultdict(list)
    for x in records:
        groups[x["repo"]].append(int(x["hit"][a])-int(x["hit"][b]))
    clusters=[(sum(g),len(g)) for g in groups.values()]
    rng=random.Random(60717)
    boots=[]
    for _ in range(20000):
        s=rng.choices(clusters,k=len(clusters))
        boots.append(sum(v for v,n in s)/sum(n for v,n in s))
    boots.sort()
    diff=Counter(d for g in groups.values() for d in g)
    return dict(wins=diff[1], losses=diff[-1], ties=diff[0],
                different_top1=sum(r["score"][a][0]!=r["score"][b][0] for r in records),
                micro_pp=100*(diff[1]-diff[-1])/len(records), macro_pp=100*statistics.mean(v/n for v,n in clusters),
                repo_boot95_pp=[100*boots[499],100*boots[19499]],mcnemar_exact=mcnemar(diff[1],diff[-1]))

def null(records,reader,gate):
    projects=defaultdict(list)
    for r in records: projects[r["repo"]].append(r)
    dist={0:1}
    expected_prompt=0.
    for project,g in projects.items():
        k=sum(r["skip_"+gate] for r in g)
        expected_prompt+=sum(r["score"][reader][1] for r in g)*(1-k/len(g))
        delta=Counter(int(r["hit"]["fusion"])-int(r["hit"][reader]) for r in g)
        ways=Counter()
        for pos in range(min(delta[1],k)+1):
            for neg in range(min(delta[-1],k-pos)+1):
                neutral=k-pos-neg
                if neutral<=delta[0]:
                    ways[pos-neg]+=math.comb(delta[1],pos)*math.comb(delta[-1],neg)*math.comb(delta[0],neutral)
        assert sum(ways.values())==math.comb(len(g),k)
        next_dist=Counter()
        for j,n in dist.items():
            for j2,n2 in ways.items(): next_dist[j+j2]+=n*n2
        dist=next_dist
    n=sum(dist.values())
    always=sum(r["hit"][reader] for r in records)
    observed=sum(r["hit"][reader+"_"+gate] for r in records)
    return dict(expected_hits=always+sum(j*m for j,m in dist.items())/n,expected_input_tokens=expected_prompt,
                prob_hit_at_least_observed=sum(m for j,m in dist.items() if j+always>=observed)/n,
                outcomes={j+always:str(m) for j,m in sorted(dist.items())},schedules=str(n))

def totals(rows):
    names=set.intersection(*(set(r["score"]) for r in rows))
    def metric(s):
        out=[]
        for r in rows:
            keys=r["positive"];v=r["score"][s][0];out.append((v in keys,v==keys[0],v==keys[-1],v in keys and len(keys)==1))
        return {**dict(zip(("any","first","last","worst_single"),map(sum,zip(*out)))),
                "calls":sum(r["score"][s][1]>0 for r in rows),"input":sum(r["score"][s][1] for r in rows),
                "output":sum(r["score"][s][2] for r in rows)}
    return {s:metric(s) for s in sorted(names)}

def panel(rows,refs):
    return dict(n=len(rows),repos=len({r["repo"] for r in rows}),in_library=sum(r["available"] for r in rows),
                multiple=sum(len(r["positive"])>1 for r in rows), in_five=sum(r["in_five"] for r in rows),
                skip_three=sum(r["skip_three"] for r in rows),skip_two=sum(r["skip_two"] for r in rows),
                results=totals(rows),paired={a+"/"+b:contrast(rows,a,b) for a,b in refs},
                per_project={p:dict(n=len(g),skips=sum(x["skip_three"] for x in g),hits={s:sum(x["hit"][s] for x in g) for s in set.intersection(*(set(x["score"]) for x in g))}) for p in sorted({x["repo"] for x in rows}) if (g:=[x for x in rows if x["repo"]==p])})

def rem_bounds(n,a,b):
    cases=[(a-both,b-both) for both in range(max(0,a+b-n),min(a,b)+1)]
    pvals=[mcnemar(w,l) for w,l in cases]
    return dict(our=a,paper=b, win_loss_endpoints=[list(cases[0]),list(cases[-1])], feasible_p=[min(pvals),max(pvals)])

def main():
    assert all(sha(HERE/n)==h for n,h in load(HERE/"decision-seal.json").items())
    plan=load(HERE/"decisions.json.gz");inputs=load(HERE/"inputs.json.gz");labels=load(HERE/"labels.json.gz")
    records=[]
    for ordinal,(p,r,y) in enumerate(zip(plan,inputs,labels,strict=True)):
        assert r["task"]==y["task"]
        positive=y["positive_ids"]
        assert positive
        score=p["scores"]
        records.append(dict(ordinal=ordinal,task=r["task"],repo=r["repo"],score=score,positive=positive,
                            available=any(x is not None for x in positive),in_five=bool(set(positive)&set(r["ranks"]["fusion"][:5])),
                            skip_three=p["skip_three"],skip_two=p["skip_two"],hit={k:v[0] in positive for k,v in score.items()}))
    lite,ext=records[:99],records[99:]
    graph=[r for r in lite if "true" in r["score"]]
    other={r["task"] for r in inputs if r.get("r59_candidates")}
    mini=[("mini_reader_three","mini_reader"),("mini_reader_three","fusion")]
    lr=[("full_three",s) for s in ("full","no_edits","recall_five","recall_hybrid","fusion","full_two")]
    graph_pairs=[(s+"_three",s) for s in ("true","flat","rotation")]+[("true_three","flat_three"),("true_three","rotation_three")]
    out={"lite":panel(lite,lr+mini),"extension":panel(ext,mini),
         "extension_available":panel([r for r in ext if r["available"]],mini),"R59_graph":panel(graph,graph_pairs),
         "r59_coverage":{"graph":len(graph),"candidate":len(other),"intersection":sum(r["task"] in other for r in graph),
                         "union":len({r["task"] for r in graph}|other)},
         "null":{"three":null(lite,"full","three"),"two":null(lite,"full","two")}}
    n=99
    scores=out["lite"]["results"]["full_three"]
    out["REM_bounds"]={str(rem):{k:rem_bounds(n,scores[k],rem) for k in ("any","worst_single","first","last")} for rem in (66,68)}
    save("per_item.json.gz",records)
    save("results.json",out)
    save("result-seal.json",{n:sha(HERE/n) for n in ("grade.py","decision-seal.json","label-source.json","labels.json.gz","per_item.json.gz","results.json")})
    for key in ("lite","extension","extension_available","R59_graph"):
        v=out[key]
        m=v["results"]
        print(key,v["n"],"skip3",v["skip_three"],"covered",v["in_library"],"shortlist",v["in_five"])
        ks=("full","full_three","full_two","recall_five","no_edits","recall_hybrid","recall_keyword","fusion","bm25_outcome","minilm","mini_reader_three","true","true_three","flat","flat_three","rotation","rotation_three")
        print({k:(m[k]["any"],m[k]["calls"],m[k]["input"]) for k in ks if k in m})
    print("primary",out["lite"]["paired"]["full_three/full"])
    print("null",out["null"]["three"]["expected_hits"],out["null"]["three"]["prob_hit_at_least_observed"])
    print("REM",out["REM_bounds"]["68"])

if __name__=="__main__": main()

