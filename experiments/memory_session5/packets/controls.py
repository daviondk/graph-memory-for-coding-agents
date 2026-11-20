"""Postulated cheap competitors score the same fixed, chronological page store."""
import re
from collections import Counter
from policy import *

CONTROLS=('pair_tail','pair_center','triple_center','definitions','joint_prior_center','joint_prior_tail','joint_uniform')
def contiguous_blocks(rs,priority,length):
    lookup={(r[0],r[1]):i for i,r in enumerate(rs)}
    before={(r[0],r[2]):i for i,r in enumerate(rs)}
    groups=[]
    for i in priority:
        page=rs[i];g=[i];j=i
        for offset in range(1,length):
            k=before.get((page[0],rs[j][1]-1)) if offset%2 else lookup.get((page[0],rs[g[-1]][2]+1))
            if k is None:break
            if offset%2:g.insert(0,k);j=k
            else:g.append(k)
        if len(g)==length:groups.append(g)
    return groups
def packed_groups(rs,groups,priority,cs,limit):
    chosen=[];used=0;seen=set()
    for g in list(groups)+[[i] for i in priority]:
        add=[i for i in g if i not in seen]
        required=sum(cs[i] for i in add)
        if not add or used+required-1>limit:continue
        chosen.extend(add);seen.update(add);used+=required
        if limit-used<8:break
    return adjust(rs,chosen,limit)
def definitions(rs,priority):
    defs=[];active=[];lastpath='';previous=0;defline=re.compile(r'^(\s*)(?:async\s+def|class|def)\s+\w+')
    for i,(p,a,b,_,body) in enumerate(rs):
        if p!=lastpath or a!=previous+1:
            defs.extend(tuple(v[1]) for v in active);active=[]
        for line in body.split('\n'):
            if not line.strip() or line.lstrip().startswith('#'):continue
            level=len(line)-len(line.lstrip());kept=[]
            for indent,ids in active:
                if level<=indent:defs.append(tuple(ids))
                else:
                    ids.add(i);kept.append((indent,ids))
            active=kept;match=defline.match(line)
            if match:active.append((level,{i}))
        lastpath=p;previous=b
    defs.extend(tuple(v[1]) for v in active)
    rank={i:n for n,i in enumerate(priority)};bounded={tuple(sorted(g)) for g in defs if 1<=len(g)<=10}
    return sorted(bounded,key=lambda g:(min(rank[i] for i in g),-len(g),g))
def heuristic_props(rs,rank,widths):
    next_idx={(r[0],r[1]):i for i,r in enumerate(rs)}
    props={}
    for j,i in enumerate(rank[:CAP]):
        q=1/(j+2);s=[i]
        for n,w in enumerate(widths):
            if n:
                r=rs[s[-1]];k=next_idx.get((r[0],r[2]+1))
                if k is None:break
                s.append(k)
            props[tuple(s)]=q*w
    return props
def extra(states,meta,t,issue,model):
    rs=pages(states['rebase']);ct=order(rs,meta);tl=order(rs,meta,'tail');cs=costs(rs)
    gs=[contiguous_blocks(rs,tl,2),contiguous_blocks(rs,ct,2),contiguous_blocks(rs,ct,3),definitions(rs,ct)]
    prs=[heuristic_props(rs,ct,model['width_fractions']),heuristic_props(rs,tl,model['width_fractions']),heuristic_props(rs,ct,[1/3]*3)]
    result={}
    for b in BUDGETS:
        ranked=[tl,ct,ct,ct];ans=[packed_groups(rs,group,r,cs,b) for group,r in zip(gs,ranked)]
        ans.extend(joint_fill(rs,cs,props,b) for props in prs);result[str(b)]=dict(zip(CONTROLS,ans))
    return result
