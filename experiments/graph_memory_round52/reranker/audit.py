"""CPU-only independent checks of observed rankings, token budgets, prompts and benchmark outcomes."""
import math
import numpy as np
from reader import h,archive
from common import *

def audit(portable=False):
    import sys
    sys.path.insert(0,str(R51/"baseline"))
    from verify import score
    seal=get("grade-seal.json");assert seal["assignments"]==20480
    for a,b,c in [("registration.json","protocol","PROTOCOL_RU.md"),("ce-seal.json","registration","registration.json"),
        ("ce-seal.json","scores","ce-scores.json.gz"),("decision-seal.json","ce","ce-seal.json"),
        ("decision-seal.json","choices","choices.json.gz"),("decision-seal.json","model","model.json"),
        ("input-seal.json","contexts","contexts.json.gz"),("input-seal.json","prompts","new-prompts.json.gz"),
        ("input-seal.json","decisions","decision-seal.json"),("answer-seal.json","inputs","input-seal.json"),
        ("answer-seal.json","answers","new-answers.json.gz"),("answer-seal.json","checks","reader-replay.json"),
        ("grade-seal.json","results","results.json"),("grade-seal.json","records","records.json.gz"),
        ("grade-seal.json","answers","answer-seal.json")]:
        assert get(a)[b]==sha(D/c)
    choices=get("choices.json.gz");ctx=get("contexts.json.gz");model=get("model.json");ce=get("ce-scores.json.gz")
    recs=get("records.json.gz");result=get("results.json");new=get("new-answers.json.gz");fresh=get("new-prompts.json.gz")
    assert set(fresh)==set(new) and all(v==h(ts) for v,ts in fresh.items())
    answers=archive();assert not set(new)&set(answers);answers.update(new)
    tokens={};pairs=0;info={};stats={}
    paths=[PANELS[p][0]/"prompts.json.gz" for p in EVAL]+[R51/f for f in ("baseline/new-prompts.json.gz","baseline/confirm/new-prompts.json.gz","frozen_ablation/new-prompts.json.gz")]+[D/"new-prompts.json.gz"]
    for f in paths:
        for k,ts in read(f).items():assert h(ts)==k and tokens.setdefault(k,ts)==ts
    for p,(src,cache) in PANELS.items():
        rank=read(src/"orders.json.gz");receipt=read(src/"catalog-receipts.json.gz")
        projection=read(src/"projection-seal.json")
        assert sha(src/"catalog-receipts.json.gz")==projection["receipts"]
        assert projection["visible"]==get("registration.json")["inputs"][p]
        if not portable:
            assert sha(cache/"catalog-input.json.gz")==projection["visible"]
            vis=read(cache/"catalog-input.json.gz")
            assert all(set(receipt[q]["titles"])=={str(i) for i,_ in cat[2]} for q,cat in vis.items())
        assert set(rank)==set(receipt)==set(ce[p])
        if p in EVAL:
            assert set(rank)==set(ctx[p])
            raw=read(src/"contexts.json.gz");gold=read(src/"gold.json.gz");tail=read(src/"reader-boundaries.json")["tail"]
            lex=read(src/"lex-orders.json.gz")
        scores=[];secs=[];ties=0
        for q,r in rank.items():
            orig=r["order"];row=ce[p][q]["scores"];scores.extend(row.values());secs.append(ce[p][q]["seconds"])
            pairs+=len(row)
            assert set(receipt[q]["titles"])==set(row)=={str(i) for i in orig}
            assert r["seed"] not in orig
            ties+=sum(x==max(row.values()) for x in row.values())>1
            if p not in EVAL:continue
            order=sorted(orig,key=lambda i:(-row[str(i)],orig.index(i)));dec=choices[p][q];edges=set(r["edges"])
            assert dec["ce"]==order[0] and dec["ce_linked"]==next((i for i in order if i in edges),order[0])
            assert dec["linked_dense"]==next((i for i in orig if i in edges),orig[0])
            for a in ("ce_graph","ce_hybrid"):
                pred={}
                for j,i in enumerate(orig):
                    k=str(i);f=[r["scores"][k],1/(1+lex[q]["question_rank"][k]),1/(1+lex[q]["snippet_rank"][k]),
                        1/(j+1),row[k],1/(1+order.index(i)),int(i in edges)]
                    pred[i]=sum(w*(v-m)/s for w,v,m,s in zip(model["models"][a]["coef"],f,model["mean"],model["scale"]))
                assert max(orig,key=pred.get)==dec[a]
            c=ctx[p][q];first=c["seed"];prev=raw[q];old_t=tokens[prev["refs"]["dense"][1]]
            prefix=old_t[:-(prev["n"]+len(tail))]
            assert h(prefix)==c["prefix"] and first==r["seed"]==prev["seed"] and c["cap"]<=c["previous"]<=prev["n"]
            z=gold[q]
            aliases,titles,supp=z if p=="2wiki" else ([z["answer"]],z["titles"],z["support_titles"])
            for a,(i,k,n) in c["refs"].items():
                ts=tokens[k];assert n==len(ts)==len(prefix)+c["cap"]+len(tail) and ts[:len(prefix)]==prefix and ts[-len(tail):]==tail
                assert i==dec[a] and i!=first
                old={target:op for target,op,_ in prev["refs"].values()}
                if i in old:assert ts==prefix+tokens[old[i]][len(prefix):len(prefix)+c["cap"]]+tail
                em,f1=score(answers[k]["answer"],aliases)
                hits={titles[i],titles[first]}&set(supp);d=recs[p][q][a]
                assert em==d["em"] and abs(f1-d["f1"])<1e-12 and int(len(hits)==len(supp))==d["full"] and abs(len(hits)/len(supp)-d["recall"])<1e-12
        info[p]=dict(n=len(rank),pairs=len(scores),top_ties=ties,score_quantiles=np.quantile(scores,[0,.25,.5,.75,1]).tolist(),
                     concurrent_http_seconds_p50_p95=np.quantile(secs,[.5,.95]).tolist())
        if p in EVAL:
            for a,d in result[p]["policies"].items():
                for m,v in d.items(): assert abs(v-math.fsum(recs[p][q][a][m] for q in rank)/len(rank))<1e-12
    replay=get("ce-replay.json");drifts=[max(abs(v-z["repeat"][k]) for k,v in z["first"].items()) for z in replay.values()]
    flips=sum(max(z["first"],key=z["first"].get)!=max(z["repeat"],key=z["repeat"].get) for z in replay.values())
    assert pairs==get("ce-seal.json")["pairs"] and len(replay)==6 and len(get("reader-replay.json"))==24
    summary=dict(panels=info,scored_pairs=pairs,ce_replay_n=len(drifts),ce_replay_max_abs=max(drifts),ce_replay_raw_top_changes=flips,
        reader_replays=24,matched_assignments=20480,unique_readers_used=len({k for pp in ctx.values() for c in pp.values() for _,k,_ in c["refs"].values()}),
        fresh_answers=len(new),grade=sha(D/"grade-seal.json"),code=sha(Path(__file__)))
    if portable:assert summary==get("audit.json")
    else:put("audit.json",summary)
    print(json.dumps(summary))
if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--portable",action="store_true",help="Check tracked corpus projections and recompute outcomes without corpus, GPU or official grader.")
    audit(ap.parse_args().portable)
