"""Second-stage intervention: expose the endpoint roles, then rival routes for the same query."""
import itertools,math
from collections import Counter,defaultdict
from features import tok, bag, key

def extra(example,node,bms,pairs,edges):
    uid,q,titles,paragraphs=example
    qq=bag(tok(q)); tt=[bag(tok(t)) for t in titles]
    bb=[bag(tok(" ".join(ss))) for ss in paragraphs]
    ww={t:math.log(1+(len(tt)+.5-sum(t in a or t in b for a,b in zip(tt,bb)))/(.5+sum(t in a or t in b for a,b in zip(tt,bb)))) for t in qq}
    total=max(.0001,sum(ww.values()))
    def coverage(words):return sum(ww[t] for t in sorted(qq&words))/total
    arcs=set()
    placebo=set()
    for (i,j),(left,right) in zip(pairs,edges):
        flip=int(key(uid+"|flip|"+"|".join(sorted((titles[i],titles[j]))))[-2:],16)%2
        for enabled,a,b in [(left,i,j),(right,j,i)]:
            if enabled:
                arcs.add((a,b))
                placebo.add((b,a) if flip else (a,b))
    def orientation(ar):
        indeg=Counter(v for u,v in ar);outdeg=Counter(u for u,v in ar)
        result={}
        raw={}
        for u,v in ar:
            su=node[u];sv=node[v]
            keep=(0,1,2,3,4,5,10)
            result[u,v]=[su[k] for k in keep]+[sv[k] for k in keep]+[outdeg[u],indeg[v],indeg[u],outdeg[v]]
            # Which title is anchored in the question? Which words can only its partner cover?
            a=.30*su[0]/2+.20*su[1]+.20*su[2]+.15*su[3]+.15*su[4]
            c1=coverage(bb[v]-tt[u])
            c2=coverage((bb[v]|tt[v])-(bb[u]|tt[u]))
            s1=a*c1
            s2=a*c2
            s3=a/(max(outdeg[u],1)*max(indeg[v],1))**.5
            raw[u,v]=(c1,c2,s1,s2,s3)
        bonus={}
        for (u,v),(c1,c2,s1,s2,s3) in raw.items():
            same_head=[r for (w,z),r in raw.items() if w==u and z!=v]
            same_tail=[r for (w,z),r in raw.items() if z==v and w!=u]
            scores=[c1,c2,s1,s2,s3]
            alt=same_head+same_tail
            bonus[u,v]=scores+[s1-max((r[2] for r in same_head),default=0.),
                               s1-max((r[2] for r in same_tail),default=0.),
                               s2-max((r[3] for r in same_head),default=0.),
                               s2-max((r[3] for r in same_tail),default=0.),
                               s3-max((r[4] for r in alt),default=0.)]
        return result,bonus
    r,c=orientation(arcs);r0,_=orientation(placebo)
    def join(i,j,fields,size):
        vals=[fields[a] for a in ((i,j),(j,i)) if a in fields]
        return [max(row[k] for row in vals) for k in range(size)] if vals else [0.]*size
    return ([[*join(i,j,r,18),*join(i,j,c,10)] for i,j in pairs],
            [join(i,j,r0,18) for i,j in pairs])

