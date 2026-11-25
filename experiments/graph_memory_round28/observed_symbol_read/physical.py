"""Balanced warm resident CPU microbenchmark for exact query-gated demand/list, index, and regex lookup."""
from collections import defaultdict,Counter
from statistics import median,mean
from time import perf_counter_ns
import random,re,sys
from common28 import *
from operators import declarations,observations,parts,NAME,STOP
from predict28 import text_of
DEF=re.compile(r"(?m)^[ \t]*(?:async[ \t]+def|def|class)[ \t]+([A-Za-z_]\w*)")
def main():
    rows=[]
    for panel in ("swe","loc"):
        qs=read(P/(panel+"-queries.json"))
        for r in read(D/(panel+"-forecasts.json.gz")):
            txt=text_of(r["file"]);lines=txt.split("\n");lo,hi=r["first"]
            calls=observations("\n".join(lines[lo-1:hi]))[1];q=qs[r["issue"]]
            terms=set().union(*(parts(w) for w in NAME.findall(q))) if q else set()
            demand={name for name in calls if parts(name)&terms};c=Counter(calls);first={}
            for j,name in enumerate(calls):first.setdefault(name,j)
            def resolve(d):
                a=[]
                for n in demand:
                    hits=[p for p in d.get(n,()) if not lo<=p<=hi]
                    if not hits:continue
                    dist=lambda p:max(lo-p,p-hi,0)
                    k=min(hits,key=lambda p:(dist(p),p));a.append((-len(parts(n)&terms),-c[n],first[n],dist(k),k,n))
                return min(a)[-2] if a else r["address"]["repeat_bm25"]
            cached=declarations(txt)
            def probed():return resolve({name:cached[name] for name in demand if name in cached})
            def eager():return resolve(declarations(txt))
            def lazy():return resolve(declarations(txt,demand))
            def regex():
                if not demand:return resolve({})
                locs=defaultdict(list);start=0;ln=1
                for match in DEF.finditer(txt):
                    if match[1] not in demand:continue
                    ln+=txt.count("\n",start,match.start());start=match.start()
                    locs[match[1]].append(ln)
                return resolve(locs)
            fs={"lookup":probed,"build":eager,"demand":lazy,"regex":regex}
            times=defaultdict(list);answers={}
            rng=random.Random(int(digest(r["issue"])[:16],16));order=list(fs);rng.shuffle(order)
            for h in range(4):
                order=order[1:]+order[:1]
                for k in order:
                    t0=perf_counter_ns();ans=fs[k]();times[k].append(perf_counter_ns()-t0)
                    if k in answers:assert answers[k]==ans
                    answers[k]=ans
            goal=r["address"]["query_call"]
            assert all(answers[k]==goal for k in ("lookup","build","demand"))
            rows.append(dict(issue=r["issue"],panel=panel,bytes=len(txt.encode()),demand_names=len(demand),spans=goal is not None,regex_equal=answers["regex"]==goal,times=times,functions=len(cached)))
    save(D/"physical-runs.json.gz",rows);summary={}
    for p in ("swe","loc"):
        group=[r for r in rows if r["panel"]==p];summary[p]={"n":len(group),"demanded_files":sum(bool(r["demand_names"]) for r in group),"bytes":sum(r["bytes"] for r in group),"demanded_bytes":sum(r["bytes"] for r in group if r["demand_names"]),"regex_mismatches":sum(not r["regex_equal"] for r in group)}
        for k in rows[0]["times"]:
            z=[median(r["times"][k])*1e-6 for r in group]
            summary[p][k]={"median_ms":median(z),"mean_ms":mean(z),"median_when_demanded_ms":median(a for a,r in zip(z,group) if r["demand_names"])}
    save(D/"physical.json",summary);print(summary)
if __name__=="__main__":main()

