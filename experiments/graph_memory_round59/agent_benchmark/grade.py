"""After sealing model responses, join chosen trajectory IDs to official issue relations."""
import csv
import hashlib
import itertools
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from roster import HERE, OLD, STAGE, get, put, sha


def pair(records,a,b):
    by=defaultdict(list);changed=0
    for r in records.values():
        by[r["repo"]].append(int(r["hit"][a])-int(r["hit"][b]))
        changed+=r["choice"][a]!=r["choice"][b]
    diff=[v for g in by.values() for v in g];wins=diff.count(1);loss=diff.count(-1)
    rng=random.Random(590113);clusters=[(sum(g),len(g)) for g in by.values()]
    bts=[]
    for i in range(20000):
        s=rng.choices(clusters,k=len(clusters));bts.append(100*sum(x for x,n in s)/sum(n for x,n in s))
    bts.sort()
    return dict(different_top1=changed,wins=wins,losses=loss,ties=len(diff)-wins-loss,
                delta_pp=100*sum(diff)/len(diff),repo_bootstrap95_pp=[bts[499],bts[19499]],
                mcnemar_p=min(1,2*sum(math.comb(wins+loss,i) for i in range(min(wins,loss)+1))/2**(wins+loss)),
                discordant_ids=[r["id"] for r in records.values() if r["hit"][a]!=r["hit"][b]])


def main():
    import pyarrow.parquet as pq
    assert all(sha(HERE/n)==h for n,h in get(HERE/"answer-seal.json").items())
    assert all(sha(HERE/n)==h for n,h in get(HERE/"prompt-seal.json")["hashes"].items())
    def oldlines(n):return [json.loads(l) for l in (OLD/n).read_bytes().splitlines()]
    old_choices={r["ordinal"]:r for r in oldlines("qwen_calls.jsonl")}
    more={(r["ordinal"],r["arm"]):r for r in oldlines("matched_reader/calls.jsonl")}
    oldr=get(OLD/"blind_ranks.json")
    external={k:get(OLD/(k+".json")) for k in ("recall_keyword","recall_hybrid")}
    hashes={}
    for k in external:
        h=sha(OLD/(k+".json"))
        assert h==get(OLD/(k+"_pin.json"))["sha256"][k+".json"]
        hashes[k]=h
    c=get(HERE/"cohort.json.gz");aa=get(HERE/"assignments.json.gz")
    pred=get(HERE/"predictions.json.gz");ans=get(HERE/"answers.json.gz");inp=get(HERE/"inputs.json.gz");graph=get(HERE/"graph.json.gz")
    assert set(pred)==set(c["tasks"])==set(aa)
    labels=defaultdict(set)
    relation=STAGE/"SWEContextBench_Relationship.parquet"
    pins=get(OLD/"source.json");files={x["relative"]:x["sha256"] for x in pins["files"]}
    assert sha(relation)==files[relation.name]
    for row in pq.read_table(relation,columns=["related_instance_id","experience_instance_id"]).to_pylist():
        labels[row["related_instance_id"]].add(row["experience_instance_id"])
    lib={r["trace_key"]:r["instance_id"] for r in csv.DictReader((OLD/"evaluation_library.csv").open(encoding="utf8"))}
    rr={};archive_cost=defaultdict(lambda:Counter())
    for num,task in c["tasks"].items():
        i=int(num);r=aa[num];choice={a:p["selected"] for a,p in pred[num].items()}
        assert all(v in r["base"] for v in choice.values())
        ori=oldr[i]
        choice.update({k:v[0] for k,v in ori.items() if k!="ordinal"})
        for k,rows in external.items():
            assert rows[i]["ordinal"]==i
            choice[k]=rows[i][k][0]
        primary=old_choices[i]
        assert set(primary["order"])==set(r["base"])
        for name,record in (("qwen27_complete",primary),("qwen27_no_edits",more[i,"no_edits"]),("qwen27_recall5",more[i,"recall_five"])):
            choice[name]=record["choice"]
            for field in ("prompt_tokens","completion_tokens"):archive_cost[name][field]+=record["usage"].get(field,0)
        gold=labels[task["id"]];assert gold
        hit={a:lib[k] in gold for a,k in choice.items()}
        rr[num]=dict(id=task["id"],repo=task["repo"],gold=sorted(gold),choice=choice,hit=hit,
                     slate=r["base"],in_slate=any(lib[k] in gold for k in r["base"]),
                     in_library=bool(set(lib.values())&gold),
                     legible=sum(k in graph for k in r["base"]),edge_candidate=sum(bool(graph.get(k,{}).get("edges")) for k in r["base"]),
                     true_and_rotation_same_input=r["arms"]["true"]==r["arms"]["rotation"],
                     degenerate_graphs=sum(k in graph and len({b for a,b in graph[k]["edges"]})<=1 for k in r["base"]),
                     fallback={a:v["fallback"] for a,v in pred[num].items()})
    put("scored.json.gz",rr)
    methods=list(next(iter(rr.values()))["choice"])
    n=len(rr)
    summary=lambda rows:{a:sum(x["hit"][a] for x in rows) for a in methods}
    repo={k:dict(n=len(g),matches=summary(g)) for k in sorted({v["repo"] for v in rr.values()}) if (g:=[x for x in rr.values() if x["repo"]==k])}
    costs={a:dict(input=sum(len(inp[x["arms"][a]]) for x in aa.values()),
                  output=sum(ans[x["arms"][a]]["output_tokens"] for x in aa.values())) for a in ("true","rotation","flat")}
    results=dict(n=n,match1=summary(list(rr.values())),per_repo=repo,
                 contrasts={"true_vs_"+b:pair(rr,"true",b) for b in methods if b!="true"},
                 slate5=sum(r["in_slate"] for r in rr.values()),available=sum(r["in_library"] for r in rr.values()),
                 eligible_sources=sum(r["legible"] for r in rr.values()),issued_cards=5*n,with_edges=sum(r["edge_candidate"] for r in rr.values()),
                 true_and_rotation_same_input=sum(r["true_and_rotation_same_input"] for r in rr.values()),
                 distinct_prompts=len(ans),actual_input_tokens=sum(map(len,inp.values())),
                 actual_output_tokens=sum(a["output_tokens"] for a in ans.values()),costs=costs,
                 older_reader_tokens=archive_cost,
                 fallback={a:sum(r["fallback"][a] for r in rr.values()) for a in costs},
                 n_sources=len(graph),retained_edges=sum(len(g["edges"]) for g in graph.values()),
                 zero_edge_source=sum(not g["edges"] for g in graph.values()),
                 original_projection=dict(relationship_sha=sha(relation),source_repo=pins["github"],source_dataset=pins["hf"],
                     historical_library=sha(OLD/"evaluation_library.csv"),
                     prior_baselines={**hashes,**{s:sha(OLD/s) for s in ("blind_ranks.json","qwen_calls.jsonl","matched_reader/calls.jsonl")}}))
    put("results.json",results)
    print(n,results["match1"],"slate",results["slate5"])
    for k in ("rotation","flat","fusion","qwen27_complete","recall_hybrid"):
        print(k,results["contrasts"]["true_vs_"+k])


if __name__=="__main__":main()
