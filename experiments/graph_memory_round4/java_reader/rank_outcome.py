"""Post hoc paired mediation diagnostic. No additional training or selection of completions."""
from collections import defaultdict
from infer import read,save,sha
def main():
    items=read("B_selective_items.json.gz")
    groups=defaultdict(list)
    for t in items:
        a,b=[t["methods"][k] for k in ("graph","semlith")]
        group={(0,0):"neither",(1,0):"only_graph",(0,1):"only_semlith",(1,1):"both"}[a["retrieved"],b["retrieved"]]
        groups[group].append(t)
    report={}
    for k,rows in groups.items():
        s={m:sum(r["methods"][m]["em"] for r in rows) for m in ("empty","graph","semlith")}
        pools=defaultdict(list)
        for r in rows:
            a,b=[r["methods"][m]["em"] for m in ("graph","semlith")]
            pools[{(1,0):"graph_only_correct",(0,1):"semlith_only_correct",(1,1):"both_correct",(0,0):"both_missed"}[a,b]].append(r)
        samples={p:{"n":len(v),"example":{w:sorted(v,key=lambda r:sha("read-diagnostic|"+r["id"]))[0][w] for w in ("id","repo")}} for p,v in pools.items()}
        report[k]={"n":len(rows),"projects":len({r["repo"] for r in rows}),"em_counts":s,"outcome_pairs":samples}
    save("rank_outcome.json",report)
    print({k:(v["n"],v["em_counts"]) for k,v in report.items()})
if __name__=="__main__":main()

