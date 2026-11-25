"""Public, ID-invariant graph features from a faulty trace, without gold or final-answer text."""
from collections import defaultdict,deque,Counter
from math import log,sqrt
import re
GROUPS={"graph":["direct","inverse_source_distance","to_final","inverse_final_distance","parents","bad_parents","fraction_bad_parents","source_ancestors_fraction"],
        "position":["last_reachable","relative_candidate_position","relative_trace_position","remaining_candidates_capped","remaining_steps_capped","candidate_count_capped"],
        "lexical":["source_cosine","unaffected_cosine","cosine_margin","direct_source_cosine","direct_unaffected_cosine","direct_margin"]}
def distances(links,roots):
    dist={x:0 for x in roots};q=deque(dist)
    while q:
        u=q.popleft()
        for v in links.get(u,()):
            if v not in dist:dist[v]=dist[u]+1;q.append(v)
    return dist

def extract(row):
    mem={x["id"]:x for x in row["memory"]};steps=row["steps"];src=set(row["diagnosis"])
    parents={m:set(v["parents"]) for m,v in mem.items()}
    for s in steps:
        parents.setdefault(s["id"],set()).update(s["parents"])
        for m in s["writes"]:
            if m in mem:parents[m].add(s["id"])
    children=defaultdict(set)
    for child,ps in parents.items():
        for p in ps:children[p].add(child)
    fwd=distances(children,src);fs=[s["id"] for s in steps if s["type"]=="final_answer"];back=distances(parents,fs[-1:]);reachable=[(j,s) for j,s in enumerate(steps) if s["type"]=="claim" and s["id"] in fwd]
    def tokens(text):
        return set(re.findall(r"[a-z0-9]+",text.lower()))
    def sim(a,b):
        if not a or not b:return 0.0
        return sum(w[t] for t in sorted(a&b))/sqrt(sum(w[t] for t in sorted(a))*sum(w[t] for t in sorted(b)))
    texts={k:tokens(v["text"]) for k,v in mem.items()}
    ctext={s["id"]:tokens(s["text"]) for _,s in reachable}
    docs=list(texts.values())+list(ctext.values());df=Counter(t for d in docs for t in d)
    w={t:(1+log((len(docs)+1)/(n+1)))**2 for t,n in df.items()}
    feats=[];idx={};pathmem={}
    for rank,(pos,s) in enumerate(reachable):
        u=s["id"];up=parents[u];anc=distances(parents,[u]);pathmem[u]=sorted(set(anc)&set(fwd)&set(mem));ta=ctext[u]
        related_sources=src&set(anc);other=set(anc)&set(mem)-set(fwd)
        def best(ids):return max((sim(ta,texts[k]) for k in sorted(ids) if k in mem),default=0.0)
        f=best(related_sources);g=best(other);fd=best(up&src);gd=best(up&set(mem)-set(fwd))
        vec=[int(bool(src&up)),1/fwd[u],int(u in back),1/(1+back[u]) if u in back else 0,len(up),len(up&set(fwd)),len(up&set(fwd))/max(1,len(up)),len(related_sources)/max(1,len(src)),
             int(rank==len(reachable)-1),(rank+1)/len(reachable),(pos+1)/len(steps),min(10,len(reachable)-rank-1),min(32,len(steps)-pos-1),min(10,len(reachable)),
             f,g,f-g,fd,gd,fd-gd]
        idx[u]=dict(zip(sum(GROUPS.values(),[]),vec))
    return dict(id=row["id"],features=idx,order=[s["id"] for _,s in reachable],source=sorted(src),memreach=sorted(set(mem)&set(fwd)),pathmem=pathmem)

