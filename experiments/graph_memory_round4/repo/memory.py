"""Candidate-local text and directed cross-candidate precedents. No repo-wide or future inputs."""
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
import numpy as np

WORD=re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
PART=re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
JP=re.compile(r"\b(?:class|interface|enum|record|def)\s+([A-Za-z_]\w*)")
JCALL=re.compile(r"\b([A-Za-z_]\w*)\s*\(")
NO=set("public private protected final static abstract return int bool boolean long short string char void class interface try catch throw throws if else while for new this super extends implements case break continue true false null def from import with in is as and not or instance self cls none true false const var list double float get set an the of and a to package override".split())
MOD=set("public private protected static async final synchronized default native abstract void class def".split())
def wt(x):return frozenset(s.lower() for s in WORD.findall(x) if s.lower() not in NO and len(s)>1)
def parts(words):return frozenset(t.lower() for w in words for t in PART.findall(w) if len(t)>1 and t.lower() not in NO)
def pp(s):return parts(WORD.findall(s))
def cos(x,y):return len(x&y)/max(1,math.sqrt(len(x)*len(y)))
def cov(x,y):return len(x&y)/max(1,len(x))

@lru_cache(1400)
def record(raw):
    alllines=raw.splitlines();words=WORD.findall(raw);cnt=Counter(t.lower() for t in words if t.lower() not in NO)
    orig_lines=[s for s in alllines if s.strip()]
    # Preserve bounded size while retaining the beginning and end of long declarations.
    lines=list(enumerate(orig_lines));lines=lines if len(lines)<=160 else lines[:120]+lines[-40:]
    sig=[];names=[];root=""
    for i,line in lines:
        dec=JP.search(line)
        if dec:
            name=dec.group(1);names.append(name)
            if not root:root=name
            sig.append(line)
        elif (set(WORD.findall(line)[:5])&MOD or line.lstrip().startswith("@")) and "(" in line:
            match=JCALL.search(line)
            if match and match.group(1).lower() not in NO:
                names.append(match.group(1));sig.append(line)
    if not root and names:root=names[0]
    root_words=pp(root)
    member_set=frozenset(n.lower() for n in names if n!=root and n.lower() not in NO)
    body=[(i,wt(s),pp(s)) for i,s in lines]
    history=[]
    before=frozenset();old_i=-2;old_line=frozenset()
    for i,s,p in body:
        if i!=old_i+1:before=frozenset();old_line=frozenset()
        history.append((s,before|old_line));before=old_line;old_line=p;old_i=i
    return dict(words=frozenset(cnt),counter=cnt,parts=parts(words),root=root.lower(),root_parts=root_words,
       members=member_set,sig=pp("\n".join(sig)),headers=wt("\n".join(orig_lines[:3])),body=body,
       history=history,size=len(raw),nlines=len(alllines),tokens=sum(cnt.values()),name_count=len(names))

def encode(texts):
    candidates=[record(s) for s in texts]
    roots=defaultdict(set)
    for i,r in enumerate(candidates):
        if r["root"]:roots[r["root"]].add(i)
    edges=[[] for _ in candidates];outgoing=[set() for _ in candidates]
    for src,c in enumerate(candidates):
        relevant=c["words"]&roots.keys()
        if not relevant:continue
        for words,antecedent in c["history"]:
            for symbol in words&relevant:
                for target in roots[symbol]:
                    if target!=src:
                        edges[target].append((src,antecedent,1/len(roots[symbol])))
                        outgoing[src].add(target)
    df=Counter(t for c in candidates for t in c["words"])
    return candidates,edges,outgoing,df

def features(code,enc,keep):
    candidates,edges,outgoing,df=enc
    lines=code.splitlines()[-keep:];q="\n".join(lines);ql=lines[-1] if lines else ""
    raw=wt(q);last=wt(ql);xp=pp(q);lp=pp(ql)
    history=[(wt(s),pp("\n".join(lines[max(0,j-2):j]))) for j,s in enumerate(lines)]
    avg=max(1,sum(c["tokens"] for c in candidates)/len(candidates));flat=[];loc=[];owned=[]
    idf=lambda t:math.log(1+(len(candidates)-df[t]+.5)/(df[t]+.5))
    for c in candidates:
        adj=1.2*(.25+.75*c["tokens"]/avg)
        score=sum(idf(t)*v*2.2/(v+adj) for t in raw&c["words"] if (v:=c["counter"][t]))
        ovr=lambda a,b:[cos(a,b),cov(a,b)]
        flat.append([score,*ovr(raw,c["words"]),*ovr(xp,c["parts"]),*ovr(last,c["words"]),
           *ovr(lp,c["parts"]),math.log1p(c["size"]),math.log1p(c["nlines"]),math.log1p(c["name_count"]),
           *ovr(raw,c["headers"]),*ovr(xp,c["sig"]),*ovr(xp,c["root_parts"]),int(c["root"] in raw),
           len(raw&c["members"]),*ovr(lp,c["root_parts"]),len(last&c["members"])])
        # Retrieve line-grained evidence from the very same text visible to every arm.
        a=[];b=[];e=[];h=[];prev=frozenset();old=-2
        for idx,l,pa in c["body"]:
            if idx!=old+1:prev=frozenset()
            a.append(cos(raw,l));b.append(cos(xp,pa));e.append(cos(lp,pa))
            h.append(cos(xp,pa|prev));prev=pa;old=idx
        local=[]
        for x in (a,b,e,h):
            top=sorted(x,reverse=True)[:3]
            local+=[max(top,default=0),sum(top)/3]
        loc.append(local)
        tr=[]
        for t,(ls,prior) in enumerate(history):
            if c["root"] in ls or ls&c["members"]:
                tr.append((cos(xp,prior),len(lines)-1-t))
        owned.append([len(tr),max([v for v,d in tr],default=0),max([1/(1+d) for v,d in tr],default=0),
           max([v/(1+math.log1p(d)) for v,d in tr],default=0)])
    activation=[max(cos(xp,c["root_parts"]),cos(xp,c["sig"]),loc[i][2],float(c["root"] in raw)) for i,c in enumerate(candidates)]
    edge=[]
    for i,events in enumerate(edges):
        values=[(cos(xp,prior)*ambiguity,activation[s]) for s,prior,ambiguity in events]
        incoming={s for s,_,_ in events}
        edge.append([math.log1p(len(events)),len(incoming),len(outgoing[i]),
                 max((v for v,a in values),default=0),max((v*a for v,a in values),default=0),
                 max((a for v,a in values),default=0),max((activation[t] for t in outgoing[i]),default=0),
                 sum(v for v,a in values)/max(1,len(values))])
    matrix=np.column_stack([flat,loc,owned,edge]).astype("float32")
    assert matrix.shape[1]==43,(matrix.shape,len(flat[0]),len(loc[0]),len(owned[0]),len(edge[0]))
    return matrix
FLAT=23
LOCAL=31
OWNER=35
