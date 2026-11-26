"""Compare frozen joint scores, a changing beam and a bounded certificate on all failures."""
from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean
import gzip
import json
import random
import sys
from pathlib import Path
from run import HERE, PRIVATE, UP, BLIND, read, put, sha
sys.path.insert(0,str(HERE.parent/"support_pairs"))
from families import decision_family, linear_family

def winner(edges, allowed, excluded, first=None):
    for j in allowed:
        a,b=edges[j]
        if a not in excluded and b not in excluded and (first is None or a in first or b in first):
            return j
    return None

def adaptive(edges, order, max_failures, include_first):
    visits=set()
    winners=set()
    def visit(banned):
        if banned in visits: return
        visits.add(banned)
        roots=[i for i in order if i not in banned][:2]
        j=winner(edges,range(len(edges)),banned,roots)
        if j is None: return
        winners.add(j)
        if len(banned)==max_failures:return
        certificate=set(edges[j])
        if include_first:certificate.update(roots)
        for member in sorted(certificate):visit(banned|{member})
    visit(frozenset())
    return sorted(winners),len(visits)

def question(edges,order):
    size=len(order); allrows=list(range(len(edges)))
    tree,_=decision_family(edges,2)
    linear=linear_family(edges,size,2)
    witness,visits=adaptive(edges,order,2,True)
    only_pair,pair_visits=adaptive(edges,order,2,False)
    prev=list(decision_family(edges,1)[0])
    completed=set(prev)
    for i in allrows:
        if len(completed)>=6:break
        completed.add(i)
    full_caches={"all":allrows,"top6":allrows[:6],"top_matched":allrows[:len(tree)],"doc_top4":[i for i in allrows if set(edges[i])<=set(order[:4])],"previous_plus_raw":sorted(completed),"linear":linear,"tree":tree}
    initial=[i for i in allrows if set(edges[i])&set(order[:2])]
    pool4=[i for i in allrows if set(edges[i])&set(order[:4])]
    dyn_caches={"initial_pool_static":(initial,False),"initial_pool_gated":(initial,True),"full_gated":(allrows,True),"pool4":(pool4,True),"adaptive_tree":(witness,True),"pair_only_tree":(only_pair,True),"raw_matched":(allrows[:len(witness)],True),"pool4_matched":(pool4[:len(witness)],True),"static_tree_gated":(tree,True)}
    records=[]
    live=set()
    static_live=set()
    for k in range(3):
        for removed in combinations(order,k):
            banned=set(removed); roots=[i for i in order if i not in banned][:2]
            full=winner(edges,allrows,banned)
            dyn=winner(edges,allrows,banned,roots)
            fixed=winner(edges,initial,banned)
            static_live.add(full);live.add(dyn)
            physical_0=initial[0]
            assert dyn is not None and full is not None
            got_full={key:winner(edges,inds,banned) for key,inds in full_caches.items()}
            got_dyn={key:winner(edges,inds,banned,roots if gated else None) for key,(inds,gated) in dyn_caches.items()}
            records.append({"k":k,"ban":sorted(banned),"full":full,"dyn":dyn,"fixed":fixed,"initial_survives":not(bool(set(edges[physical_0])&banned)),"full_got":got_full,"dyn_got":got_dyn})
    assert set(witness)==live and len(witness)<=visits<=13
    assert set(tree)==static_live and static_live<=set(linear) and len(linear)<=6 and len(tree)<=6
    for r in records:
        assert all(r["full_got"][a]==r["full"] for a in ("tree","linear","all"))
        assert all(r["dyn_got"][a]==r["dyn"] for a in ("adaptive_tree","pool4","full_gated"))
    return {"n":size,"full_sizes":{a:len(v) for a,v in full_caches.items()},"dyn_sizes":{a:len(v[0]) for a,v in dyn_caches.items()},"dyn_tree":witness,"dyn_pair_only":only_pair,"static_tree":tree,"visits":visits,"pair_only_visits":pair_visits,"records":records}

def main():
    plan=read(HERE/"plan.json"); dynplan=read(HERE/"dynamic-plan.json");seal=read(HERE/"ranking-seal.json")
    assert sha(HERE/"DYNAMIC_PROTOCOL_RU.md").lower()==dynplan["protocol"].lower() and dynplan["forecasts"]==0
    assert sha(HERE/"plan.json")==seal["plan"] and sha(HERE.parent/"support_pairs"/"families.py")==plan["families"]
    results={}
    for q,expected in seal["forecasts"].items():
        path=HERE/"forecasts"/(q+".json");assert sha(path)==expected
        data=read(path);rec=data["full"]; edges=[p[:2] for p in rec["pairs"]];result=question(edges,rec["doc_order"])
        result["stage"]=data["stage"];results[q]=result
    put(HERE/"outcomes.json",results)
    put(HERE/"measurement-seal.json",{"forecast_seal":sha(HERE/"ranking-seal.json"),"dynamic_plan":sha(HERE/"dynamic-plan.json"),"measure_code":sha(Path(__file__)),"outcomes":sha(HERE/"outcomes.json")})
    labels=Path("D:/CodexResearch/x20-r31-hotpot/labels.json.gz")
    with gzip.open(labels,"rt",encoding="utf8") as f: gold=json.load(f)
    with gzip.open(BLIND,"rt",encoding="utf8") as f:obs=json.load(f)
    official=read(UP/"hotpot_pred_best_retr.json")
    aggregate={}
    for group in ("pilot","replication","all"):
        qs=[q for q,r in results.items() if group=="all" or r["stage"]==group]
        if not qs:continue
        dd={"nq":len(qs),"k":{},"qual":Counter(),"resources":[],"sizes":{}}
        for side in ("full_sizes","dyn_sizes"):
            dd["sizes"][side]={key:[results[q][side][key] for q in qs] for key in results[qs[0]][side]}
        for k in (0,1,2):
            a=Counter(); d=Counter(); st=Counter(); dn=Counter(); counts=0
            by_q=[]
            for q in qs:
                local=Counter()
                for r in results[q]["records"]:
                    if r["k"]!=k:continue
                    counts+=1
                    a.update({m:int(y==r["full"]) for m,y in r["full_got"].items()})
                    d.update({m:int(y==r["dyn"]) for m,y in r["dyn_got"].items()})
                    st.update({m:int(y is None) for m,y in r["full_got"].items()})
                    dn.update({m:int(y is None) for m,y in r["dyn_got"].items()})
                    local.update({"full_diff_dynamic":int(r["full"]!=r["dyn"]),"initial_open_diff_dynamic":int(r["fixed"]!=r["dyn"]),"initial_survives_but_dynamic_changes":int(r["initial_survives"] and r["dyn"]!=results[q]["records"][0]["dyn"])})
                by_q.append(dict(local))
            dd["k"][k]={"states":counts,"full_exact":dict(a),"dynamic_exact":dict(d),"full_empty":dict(st),"dynamic_empty":dict(dn),"contrasts_by_question":by_q}
        for q in qs:
            f=read(HERE/"forecasts"/(q+".json"));r=f["full"];edges=[set(p[:2]) for p in r["pairs"]]
            refs=set(gold[q]["support"]);titles=obs[q]["titles"];true={j for j,t in enumerate(titles) if t in refs}; assert len(true)==len(refs)==2
            dynamic=edges[results[q]["records"][0]["dyn"]];baseline=set(official[q])
            dd["qual"].update({"full_exact":int(edges[0]==true),"native_beam2_exact":int(dynamic==true),"authors_released_top1_exact":int(baseline==true),"beam2_vs_authors":int(dynamic==baseline),"allpairs_vs_authors":int(edges[0]==baseline),"score_ties":r["score_ties"]})
            dd["resources"].append({"id":q,"s":f["wall_s"],"max_rss_bytes":f["rss_peak_bytes"],"forwards":len(f["encoder_calls"]),"pair_tokens":sum(x[0] for x in f["encoder_calls"]),"tree_visits":results[q]["visits"]})
        aggregate[group]=dd
    put(HERE/"results.json",aggregate)
    print(json.dumps(aggregate["all"]["qual"]),len(results),"questions",flush=True)

def stress():
    rng=random.Random(3181); totals=Counter()
    for n in range(5,11):
        for _ in range(250):
            o=list(range(n));rng.shuffle(o);e=list(combinations(range(n),2));rng.shuffle(e)
            r=question(e,o);totals[n]+=int(len(r["dyn_tree"])>len(r["dyn_pair_only"]))
    print("1500 complete randomly ordered graphs verified; adaptive tree contains more winners",dict(totals))

if __name__=="__main__":
    if "--stress" in sys.argv:stress()
    else:main()
