"""Relate pre-sealed source selection to end-to-end correctness without equating input evidence and semantic decisions."""
from setup29 import D,P,sha,read,save,Path
from collections import defaultdict,Counter
def main():
    rs=read(D/"score-rows.json.gz");m=defaultdict(Counter);joint={};cost=defaultdict(Counter)
    for r in rs:
        if "grade" not in r or not r["mode"].startswith("dim"):continue
        arm=r["arm"];q=r["q"];joint.setdefault(q,{})[arm]=r
        ny="capped" if r["finish_reason"]=="length" else "completed"
        cost[arm][ny+"_n"]+=1;cost[arm][ny+"_passes"]+=r["pass_proxy"]
        if arm=="O":continue
        for criterion in ("source","literal"):
            category= ("both" if r["old_"+criterion] else "new_only") if r["new_"+criterion] else ("old_only" if r["old_"+criterion] else "neither")
            m[arm+"/"+criterion+"/"+category]["n"]+=1;m[arm+"/"+criterion+"/"+category]["accepted"]+=r["pass_proxy"]
    uncapped=[q for q,aa in joint.items() if all(aa[arm]["finish_reason"]!="length" for arm in ("H","T","G"))]
    z={"source":sha(D/"score-rows.json.gz"),"code":sha(Path(__file__)),"native_buckets":m,"native_by_generation_end":cost,
       "native_all_blind_arms_uncapped":{a:sum(joint[q][a]["pass_proxy"] for q in uncapped) for a in ("H","T","G")},
       "native_all_blind_arms_uncapped_n":len(uncapped)}
    save(D/"evidence-application.json",z)
if __name__=="__main__":main()
