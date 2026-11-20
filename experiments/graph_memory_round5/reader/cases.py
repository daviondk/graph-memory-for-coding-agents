"""Deterministic post-hoc examples, direction counts and shared-token cost of the two-step read."""
import json
from infer import read,save,sha
def main():
    out={};cost={}
    for k,arms in [("A",("edge","local")),("B",("edge","local")),("C",("verified","draft_lex")),("F",("budget","fixed"))]:
        rows=read(k+"_items.json.gz");a,b=arms
        for sign in [-1,1]:
            subs=[x for x in rows if x["methods"][a]["em"]-x["methods"][b]["em"]==sign]
            if subs:
                x=min(subs,key=lambda x:sha("r5-case|"+x["id"]))
                out[k+str(sign)]={n:x[n] for n in ("id","repo","gold")}|{m:x["methods"][m]["line"] for m in arms}
        if k=="C":
            for arm in rows[0]["methods"]:
                need=["empty",arm] if arm in ("verified","draft_lex","static_focus") else [arm]
                cost[arm]={f:sum(sum(x["methods"][a][f] for a in need) for x in rows)/len(rows) for f in ["prompt_tokens","reply_tokens"]}
    save("cases.json",out);save("C_cost_per_policy.json",cost)
if __name__=="__main__":main()

