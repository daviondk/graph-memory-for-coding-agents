"""Evaluate locked choices and the full fixed-k prediction sets using public relation keys."""
from collections import Counter, defaultdict
import csv
import json
import math
import random
import statistics
from select_slates import HERE,FIRST,STAGE,OLD,get,put,sha


def interval(rows,a,b,metric):
    by=defaultdict(list)
    for r in rows:
        d=r["outcome"][a][metric]-r["outcome"][b][metric]
        by[r["repo"]].append(d)
    all_d=[d for group in by.values() for d in group]
    g=[(sum(v),len(v)) for v in by.values()];rng=random.Random(590223);boot=[]
    for _ in range(20000):
        sm=rng.choices(g,k=len(g));boot.append(100*sum(d for d,_ in sm)/sum(n for _,n in sm))
    boot.sort()
    w=sum(d>0 for d in all_d);l=sum(d<0 for d in all_d)
    return dict(wins=w,losses=l,ties=len(all_d)-w-l,delta_pp=100*statistics.mean(all_d),
                repo_boot95_pp=[boot[499],boot[19499]],
                sign_p=min(1,2*sum(math.comb(w+l,i) for i in range(min(w,l)+1))/2**(w+l)))


def main():
    import pyarrow.parquet as pq
    assert all(sha(HERE/n)==h for n,h in get(HERE/"answer-seal.json").items())
    assert all(sha(HERE/n)==h for n,h in get(HERE/"prompt-seal.json")["hashes"].items())
    roles=get(HERE/"roster.json.gz");slates=get(HERE/"slates.json.gz");pred=get(HERE/"predictions.json.gz")
    priors=get(OLD/"blind_ranks.json")
    source=get(OLD/"source.json")
    target=STAGE/"SWEContextBench_Relationship.parquet"
    assert sha(target)=={v["relative"]:v["sha256"] for v in source["files"]}[target.name]
    rel=defaultdict(set)
    for r in pq.read_table(target,columns=["related_instance_id","experience_instance_id"]).to_pylist():
        rel[r["related_instance_id"]].add(r["experience_instance_id"])
    vol={r["trace_key"]:r["instance_id"] for r in csv.DictReader((OLD/"evaluation_library.csv").open(encoding="utf8"))}
    def rows(p):return [json.loads(x) for x in (OLD/p).read_bytes().splitlines()]
    old27={r["ordinal"]:r for r in rows("qwen_calls.jsonl")}
    alt={(r["ordinal"],r["arm"]):r for r in rows("matched_reader/calls.jsonl")}
    ext={k:get(OLD/(k+".json")) for k in ("recall_hybrid","recall_keyword")}
    sc={};native=tuple(next(iter(slates.values())))
    def tally(ids,top,gold):
        hit={vol[k] for k in ids} & gold
        return dict(hit5=bool(hit),recall5=len(hit)/len(gold),match1=vol[top] in gold)
    for q,record in roles["tasks"].items():
        i=int(q);gold=rel[record["id"]];assert gold
        plan={**slates[q]};c={a:v["choice"] for a,v in pred[q].items()}
        for k in ext:
            assert get(OLD/(k+"_pin.json"))["sha256"][k+".json"]==sha(OLD/(k+".json"))
            plan[k]=ext[k][i][k][:5];c[k]=plan[k][0]
        for k,items in priors[i].items():
            if k in ("fusion","ordinal"):continue
            plan[k]=items[:5];c[k]=plan[k][0]
        for k,r in (("qwen27_complete",old27[i]),("qwen27_no_edits",alt[i,"no_edits"]),("qwen27_recall5",alt[i,"recall_five"])):
            plan[k]=r.get("base_slate",r["order"])[:5];c[k]=r["choice"]
        assert set(plan["qwen27_complete"])==set(plan["fusion"])
        # Preserve the original one-stage unreranked fusion output as another comparator.
        plan["fusion_rank"]=plan["fusion"];c["fusion_rank"]=plan["fusion"][0]
        sc[q]=dict(id=record["id"],repo=record["repo"],gold=sorted(gold),choices=c,slates=plan,
                   outcome={a:tally(k,c[a],gold) for a,k in plan.items()},available=bool(gold&set(vol.values())),
                   covered_by_common_four=any(vol[k] in gold for k in plan["fusion"][:4]),
                   returned_gold={a:sorted({vol[k] for k in s}&gold) for a,s in plan.items()})
    put("scored.json.gz",sc)
    rr=list(sc.values());labels=list(rr[0]["outcome"])
    def stats(sub):
        return {a:{m:sum(r["outcome"][a][m] for r in sub) if m!="recall5" else statistics.fmean(r["outcome"][a][m] for r in sub)
                   for m in ("hit5","recall5","match1")} for a in labels}
    counts={}
    for b in ("fusion","vertex","rotation"):
        counts[b]=dict(different_fifth=sum(r["slates"]["true"][4]!=r["slates"][b][4] for r in rr),
                       different_top1=sum(r["choices"]["true"]!=r["choices"][b] for r in rr),
                       gained_gold=sum(len(set(r["returned_gold"]["true"])-set(r["returned_gold"][b])) for r in rr),
                       lost_gold=sum(len(set(r["returned_gold"][b])-set(r["returned_gold"]["true"])) for r in rr),
                       metrics={m:interval(rr,"true",b,m) for m in ("hit5","recall5","match1")})
    aa=get(HERE/"assignments.json.gz");ans=get(HERE/"answers.json.gz");inp=get(HERE/"inputs.json.gz")
    res=dict(n=len(rr),matched=stats(rr),by_repo={repo:dict(n=len(v),results=stats(v)) for repo in sorted({r["repo"] for r in rr})
                if(v:=[r for r in rr if r["repo"]==repo])},contrasts=counts,
             common_four=sum(r["covered_by_common_four"] for r in rr),available=sum(r["available"] for r in rr),
             new_projection_sources=len(get(HERE/"new-graphs.json.gz")),pool_size=len(roles["eligible_source_ids"]),
             multi_gold=sum(len(r["gold"])>1 for r in rr),unique_generations=len(ans),
             actual_prompt_tokens=sum(map(len,inp.values())),actual_response_tokens=sum(v["output_tokens"] for v in ans.values()),
             per_arm_tokens={a:sum(len(inp[v[a]["hash"]]) for v in aa.values()) for a in native},
             fallback={a:sum(r[a]["fallback"] for r in pred.values()) for a in native},relation_source_sha=sha(target))
    put("results.json",res)
    print("tasks",len(rr),"shared four",res["common_four"],"multi-gold",res["multi_gold"])
    for a in ("fusion","vertex","true","rotation","qwen27_complete","recall_hybrid","fusion_rank"):
        print(a,res["matched"][a])
    print(json.dumps(counts))


if __name__=="__main__":main()
