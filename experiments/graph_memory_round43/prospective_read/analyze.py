from collections import Counter,defaultdict
from itertools import product
from common import *
from grade import PAIRS

def stats(part):
    repo=defaultdict(list);issues=defaultdict(list);arms={m:Counter() for m in METHODS+("oracle",)}
    demand=Counter()
    for r in part:
        repo[r["repo"]].append(r);issues[r["issue"]].append(r)
        for m,s in r["scores"].items():arms[m].update(s)
        demand.update({n:r[n] for n in ("observed","novel_demand","demand_lines","views","pool_upper","closed")})
    rg=[grp for _,grp in sorted(repo.items())];ig=[grp for _,grp in sorted(issues.items())]
    ix=np.array(list(product(range(len(rg)),repeat=len(rg))))
    rng=np.random.default_rng(431073);draw=rng.integers(len(ig),size=(10000,len(ig)))
    paired={}
    for m,b in PAIRS:
        key=m+"_minus_"+b
        def signed(r):return r["scores"][m]["hit"]-r["scores"][b]["hit"]
        rd=np.array([sum(map(signed,g))/len(g) for g in rg])
        idel=np.array([sum(map(signed,g))/len(g) for g in ig])
        overlaps={repo_key:{"n":len(group),"m":sum(x["scores"][m]["hit"] for x in group),"b":sum(x["scores"][b]["hit"] for x in group)}
                  for repo_key,group in sorted(repo.items())}
        paired[key]=dict(micro=sum(map(signed,part))/len(part),repo_macro=float(rd.mean()),
              repo_ci=np.quantile(rd[ix].mean(1),[.025,.975]).tolist(),issue_macro=float(idel.mean()),
              issue_ci=np.quantile(idel[draw].mean(1),[.025,.975]).tolist(),
              wins=sum(signed(r)>0 for r in part),losses=sum(signed(r)<0 for r in part),
              identification=[sum(r["bounds"][key][i] for r in part)/len(part) for i in (0,1)],
              repo_identification=[float(np.mean([sum(r["bounds"][key][i] for r in g)/len(g) for g in rg])) for i in (0,1)],
              repo=overlaps)
    return dict(n=len(part),issues=len(ig),repos=len(rg),demand=demand,methods=arms,contrasts=paired)
def main():
    obj=read(D/"outcomes.json.gz");assert sha(D/"outcomes.json.gz")==read(D/"grade-seal.json")["rows"]
    panels={}
    for n,match in (("all2696",lambda r:True),("held1071",lambda r:r["held"]),("closed",lambda r:r["closed"]),
                   ("censored",lambda r:not r["closed"]),("actual_demand",lambda r:r["observed"]),
                   ("with_possible_lines",lambda r:r["pool_upper"])):
        subset=[r for r in obj.values() if match(r)]
        if subset:panels[n]=stats(subset)
    save("results.json",dict(primary="all2696/model_minus_near/repo_macro",panels=panels,grade=sha(D/"grade-seal.json"),
                             resampling=dict(repo="exact ordered n^n resamples",issue_boot=10000,seed=431073)))
    for name,r in panels.items():print(name,r["n"],r["demand"]["pool_upper"],{m:[s["hit"],s.get("lines",0)] for m,s in r["methods"].items()})
if __name__=="__main__":main()

