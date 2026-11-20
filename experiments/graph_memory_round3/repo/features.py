"""Static, pure-text observations. No candidate or query text is executed."""
import hashlib, math, pathlib, re, sys
from collections import Counter, defaultdict
from functools import lru_cache
import numpy as np
D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D/"lib"))
from tokenizers import Tokenizer
TOKENIZER=Tokenizer.from_file(str(D/"inputs/codegen_tokenizer.json"))
WORD=re.compile(r"[A-Za-z_]\w*")
DEF=re.compile(r"^\s*(?:async\s+)?(class|def)\s+([A-Za-z_]\w*)",re.M)
ASSIGN=re.compile(r"(?<!\w)([A-Za-z_]\w*)\s*(?::[^=\n]+)?=\s*(?:[\w]+\.)*([A-Za-z_]\w*)\s*\(")
DOT=re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)")
SPLIT=re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
STOP=set("def class and or not from import with as assert if else elif return for in is None True False self cls a the to of at str int float list dict set print try except raise pass finally".lower().split())
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
def words(txt):return [w.lower() for w in WORD.findall(txt) if w.lower() not in STOP]
def pieces(seq):return {t.lower() for w in seq for t in SPLIT.findall(w.replace("_"," ")) if len(t)>1 and t.lower() not in STOP}
def tokens(txt):return frozenset(TOKENIZER.encode(txt,add_special_tokens=False).ids)
def jac(x,y):
    n=len(x&y);d=len(x)+len(y)-n
    return n/d if d else 0.
def cover(x,y):return len(x&y)/max(1,len(x))
@lru_cache(3000)
def describe(txt):
    cf=Counter(words(txt));keys=set(cf);parts=pieces(WORD.findall(txt));defs=DEF.findall(txt)
    root=defs[0][1].lower() if defs else "";members={n.lower() for _,n in defs[1:]}-STOP
    header="\n".join(txt.splitlines()[:3]);header_tokens=set(words(header))
    return (cf,keys,parts,tokens(txt),root,members,header_tokens,len(txt),len(txt.splitlines()),len(defs))
def view(code,n):
    lines=code.split("\n")[-n:];sets=[set(words(l)) for l in lines]
    raw=[set(WORD.findall(l)) for l in lines]
    modules=[ASSIGN.findall(l) for l in lines];dots=[DOT.findall(l) for l in lines]
    joined="\n".join(lines);tail=[lines[-r:] for r in (3,10,40,120)]
    qsets=[set(words("\n".join(s))) for s in tail];qparts=[pieces(WORD.findall("\n".join(s))) for s in (tail[0],tail[-1])]
    anchors=[l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    # A transition is from a completed prefix to the next observed line that uses a declaration.
    pred=[]
    target=set(words("\n".join(lines[-3:])));target_tail=set(words(anchors[-1])) if anchors else set()
    for i in range(len(lines)):
        hist=set().union(*sets[max(0,i-3):i])
        last=sets[i-1] if i else set()
        pred.append(.65*jac(hist,target)+.35*jac(last,target_tail))
    shift=1+int(sha(joined+"|placebo")[:12],16)%max(1,len(lines)-1) if len(lines)>1 else 0
    return lines,sets,raw,modules,dots,qsets,qparts,tokens("\n".join(tail[0])),tokens(joined),pred,shift
def compute(code,contexts,n):
    cr=[describe(c) for c in contexts]
    lines,sets,raw,mods,dots,qs,qparts,bq3,bqn,pred,shift=view(code,n)
    N=len(cr);df=Counter(t for s in cr for t in s[1]);avg=max(1,sum(sum(s[0].values()) for s in cr)/N)
    name_owners=defaultdict(set);mem_owners=defaultdict(set)
    for j,s in enumerate(cr):
        if s[4]:name_owners[s[4]].add(j)
        for t in s[5]:mem_owners[t].add(j)
    tracks=[[] for s in cr];tmap={}
    for i,(ls,bindings,dd) in enumerate(zip(sets,mods,dots)):
        hits=defaultdict(float)
        for word in ls:
            for j in name_owners.get(word,()):hits[j]=max(hits[j],1.0/len(name_owners[word]))
        for v,m in dd:
            ml=m.lower()
            for j in mem_owners.get(ml,()):
                hits[j]=max(hits[j],1.0 if j in tmap.get(v.lower(),()) else .52/len(mem_owners[ml]))
        for k,v in bindings:tmap[k.lower()]=name_owners.get(v.lower(),set())
        for j,wt in hits.items():
            if wt:tracks[j].append((i,wt))
    rows=[]
    for j,(freq,terms,part,bt,root,mem,header,size,nlines,ndefs) in enumerate(cr):
        l=sum(freq.values());den=1.5*(.25+.75*l/avg)
        def bm(q):
            return sum(math.log((N-df[t]+.5)/(df[t]+.5)+1)*2.5*freq[t]/(freq[t]+den) for t in q if t in freq)
        bm3,bm120=bm(qs[0]),bm(qs[-1]);j3,jn=jac(bq3,bt),jac(bqn,bt)
        flat=[j3,jn,bm3,bm120,math.log1p(size),math.log1p(nlines),math.log1p(ndefs),
              *(jac(q,terms) for q in qs),*(cover(q,terms) for q in qs),
              *(cover(q,part) for q in qparts),*(cover(q,header) for q in (qs[0],qs[-1])),
              *(int(root in q) for q in qs),*(len(q&mem) for q in qs),len(mem)]
        tr=tracks[j];L=len(lines)
        own=[len(tr),max([wt for i,wt in tr],default=0),max([wt/(1+math.log1p(L-1-i)) for i,wt in tr],default=0),
             sum(wt for i,wt in tr),int(any(j in owner for owner in tmap.values())),min([L-1-i for i,wt in tr],default=130)]
        def transition(off):
            val=[wt*pred[(i+off)%L] for i,wt in tr]
            return [max(val,default=0),sum(val)/max(1,sum(w for _,w in tr)),sum(v>0.1 for v in val),max([v/(1+math.log1p(L-1-i)) for v,(i,wt) in zip(val,tr)],default=0)]
        rows.append(flat+own+transition(0)+transition(shift))
    return np.asarray(rows,dtype=np.float32)
BASE=28; OWN=6; EDGE=4

