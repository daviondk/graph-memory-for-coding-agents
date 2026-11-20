"""Post-hoc frontier ablation with fixed historical task denominators."""
from collections import Counter,defaultdict
import random
from common import *
from java_parse import address,locate,project
from predict import rank
from score import get_target

ARMS=("lex_prior","edge","edge_lex_agree")
def report(rs):
    out=dict(n=len(rs),available=sum(r["available"] for r in rs),sha_bytes=sum(r["bytes"] for r in rs),
             files=sum(r["paths"] for r in rs),commits=len({r["commit"] for r in rs}),arms={})
    for arm in ARMS:
        out["arms"][arm]=dict(joint=sum(r["joint"][arm] for r in rs),address=sum(r["correct_address"][arm] for r in rs),
                             fp=sum(not r["inline"] and r["available"] and r["flags"][arm] for r in rs),
                             tp=sum(r["inline"] and r["available"] and r["flags"][arm] for r in rs))
    return out
def compare(rs,cost):
    blocks=defaultdict(lambda:[0,0,0,0])
    by_case=defaultdict(dict)
    for r in rs:by_case[r["case"]][r["budget"]]=r
    for _,d in by_case.items():
        x,y=d[cost],d[8]
        b=blocks[y["commit"]];b[0]+=x["joint"]["lex_prior"]-y["joint"]["lex_prior"]
        b[1]+=1;b[2]+=y["bytes"]-x["bytes"];b[3]+=y["bytes"]
    def metrics(v):
        a,n,s,t=map(sum,zip(*v));return [100*a/n,100*s/t]
    values=list(blocks.values());rng=random.Random(19021)
    sample=[sorted(v) for v in zip(*(metrics(rng.choices(values,k=len(values))) for _ in range(10000)))]
    return dict(zip(("joint_change_pp","bytes_saved_percent"),[
        dict(point=p,ci95=[b[249],b[9749]]) for p,b in zip(metrics(values),sample)]))
def run(folder):
    def get(f):return read(folder/f)
    src=get("sources.json.gz"); truth={r["case"]:r for r in get("outcomes.json")}
    labels=get("labels.json");rows=[]
    for q in get("queries.json"):
        case=q["case"]
        if case not in truth:continue
        r=src[q["commit"]];inline=truth[case]["inline"]
        for budget in (1,2,4,8):
            chosen=r["selected"][case][:budget]
            prior,current,stats=project(r,chosen)
            matched=locate(prior,q["source"])
            addr={k:None for k in ARMS};flags={k:None for k in ARMS}
            if len(matched)==1:
                pick=rank(r,q,prior,current,prior[matched[0]],stats)
                addr={k:pick["addresses"][k] for k in ARMS}
                flags={k:pick["roles"][k] for k in ARMS}
            # Fixed external gold resolved at maximum frontier, never narrowed when scoring a smaller frontier.
            gold=truth[case]["gold"]
            hits={k:bool(gold is not None and a==gold) for k,a in addr.items()}
            joint={k:bool(hits[k] and flags[k]==inline) for k in ARMS}
            if budget==8:
                assert all(hits[k]==truth[case]["address_hit"][k] and joint[k]==truth[case]["joint_hit"][k]
                           and flags[k]==truth[case]["predicted"][k] for k in ARMS)
            cost=sum(r["files"][str(i)][s+"_blob"]["size"] for i in chosen for s in ("old","new") if r["files"][str(i)][s])
            assert cost==stats["bytes_input"]
            rows.append(dict(case=case,panel=str(folder),commit=q["commit"],project=q["project"],budget=budget,
                             paths=len(chosen),bytes=cost,inline=inline,available=len(matched)==1,flags=flags,
                             correct_address=hits,joint=joint))
    return rows,dict(metrics={str(b):report([r for r in rows if r['budget']==b]) for b in (1,2,4,8)},
                     comparisons={str(k):compare(rows,k) for k in (1,2,4)})
def main():
    rs=[];out={}
    for panel,folder in [("primary",Path(".")),("holdout",Path("holdout"))]:
        r,out[panel]=run(folder);rs.extend(r)
    save("budget-rows.json.gz",rs);save("budget-results.json",out)
    save("budget-lock.json",hashfiles(["BUDGET_PROTOCOL_RU.md","budget.py","budget-rows.json.gz","budget-results.json",
                                      "score-lock.json","holdout/score-lock.json"]))
    for panel,x in out.items():
        print(panel,[(n,v["available"],v["arms"]["lex_prior"]["joint"],v["sha_bytes"]) for n,v in x["metrics"].items()],x["comparisons"]["1"])
if __name__=="__main__":main()
