"""Append-only titled passages and their sentence-scoped references; no labels or answer text."""
import hashlib
import html
import itertools
import math
import re
import unicodedata
from collections import Counter, defaultdict
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

STOP = frozenset(ENGLISH_STOP_WORDS) | {"did","does","said","known","named"}
WORD = re.compile(r"[^\W_]+", re.UNICODE)
def key(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
def tok(text):
    text=unicodedata.normalize("NFKC",html.unescape(text)).casefold()
    return tuple(WORD.findall(text))
def numeric_token(t):
    return len(t)>1 and t.isdigit()
def stem(t):
    if len(t)>5 and t.endswith("ies"):return t[:-3]+"y"
    if len(t)>5 and t.endswith("s") and not t.endswith("ss"):return t[:-1]
    return t
def bag(tokens):
    return {stem(t) for t in tokens if t not in STOP and len(t)>1}
def bcount(tokens):
    return Counter(stem(t) for t in tokens if t not in STOP and len(t)>1)
def alias(title):
    return re.sub(r"\s*\([^()]*\)\s*$","",title).strip()
def match_seq(row, title):
    n=len(title)
    return n>0 and any(row[p:p+n]==title for p,t in enumerate(row) if t==title[0])
class EvidenceGraph:
    """Postings on first words plus old sentence positions support references in either order."""
    def __init__(self,titles):
        self.titles=titles
        self.forms={}
        self.potential=defaultdict(set)
        self.sentpos=defaultdict(list)
        self.sentences={}
        self.edges=defaultdict(set)
    def add(self,i,sentences):
        assert i not in self.sentences
        self.sentences[i]=sentences
        t=self.titles[i]
        full=tok(t); short=tok(alias(t))
        if full:self.forms[i]=(full,short)
        for form in set(self.forms.get(i,())):
            if not form or not bag(form):continue
            for other,sidx in self.sentpos.get(form[0],()):
                if match_seq(self.sentences[other][sidx],form):
                    self.edges[other,i].add((sidx,form))
            self.potential[form[0]].add((i,form))
        for sidx,words in enumerate(sentences):
            for first in set(words):
                for other,form in self.potential.get(first,()):
                    if other!=i and match_seq(words,form):
                        self.edges[i,other].add((sidx,form))
                self.sentpos[first].append((i,sidx))
    def resolve(self):
        # Ambiguity can become known when a later title arrives. Validate at read time.
        owners=defaultdict(set)
        for i,forms in self.forms.items():
            for f in forms:owners[f].add(i)
        resolved={}
        for (i,j),obs in self.edges.items():
            full=self.forms[j][0]
            ok={pos for pos,f in obs if f==full or len(owners[f])==1}
            if ok:resolved[i,j]=sorted(ok)
        return resolved

def pair_features(example, insertion=None):
    uid,question,titles,texts=example
    n=len(titles)
    ww=[tuple(tok(s) for s in ss) for ss in texts]
    graph=EvidenceGraph(titles)
    for i in (range(n) if insertion is None else insertion):
        graph.add(i,ww[i])
    links=graph.resolve()
    indeg=Counter(j for i,j in links); outdeg=Counter(i for i,j in links)
    qseq=tok(question);q=bag(qseq);tp=[tok(t) for t in titles];title=[bag(z) for z in tp]
    sentences=[[bag(words) for words in ss] for ss in ww]
    tf=[bcount(itertools.chain.from_iterable(ss)) for ss in ww]
    body=[set(c) for c in tf]
    support=[a|b for a,b in zip(body,title)]
    idf={t:math.log(1+(n+0.5-sum(t in d for d in support))/(0.5+sum(t in d for d in support))) for t in q}
    weights=lambda ts:sum(idf[t] for t in sorted(ts) if t in idf)
    norm=max(weights(q),.0001)
    def frac(ts):return weights(ts)/norm
    meanlen=sum(sum(c.values()) for c in tf)/max(1,n)
    bms=[]; node=[]
    pattern=("both" in qseq or "either" in qseq or " or " in (" "+" ".join(qseq)+" ") or "same" in qseq)
    qset=set(qseq)
    meta=[float(pattern),float("who" in qset),float("when" in qset),float("where" in qset),
          float("which" in qset),float(bool(re.search(r"\b(?:earlier|later|first|older|younger|longer)\b",question,re.I))),len(q)]
    for i in range(n):
        nt=sum(tf[i].values())
        bm=0.
        for t in sorted(q):
            x=tf[i][t]+2*(t in title[i])
            bm+=idf[t]*2.2*x/(x+1.2*(.25+.75*nt/max(meanlen,.01)))
        bms.append(bm)
        scores=[frac(s) for s in sentences[i]]
        top=sorted(scores,reverse=True)
        ti=title[i]
        node.append([bm/norm,frac(support[i]),frac(ti),len(q&ti)/max(len(ti),1),
                     float(match_seq(qseq,tok(alias(titles[i])))),top[0] if top else 0,
                     top[1] if len(top)>1 else 0,frac(q&body[i]-ti),nt/150,len(scores)/5,
                     frac(ti|q.intersection(sentences[i][0] if scores else set()))])
    def direction(i,j,placebo):
        pos=links.get((i,j),[])
        if not pos:return [0.]*7
        if placebo and len(ww[i])>1:
            offset=1+int(key(uid+"|"+titles[i]+"|"+titles[j])[:8],16)%(len(ww[i])-1)
            pos=sorted({(k+offset)%len(ww[i]) for k in pos})
        terms=q-title[j]-title[i]
        companion=q&support[j]
        comps=[frac(z) for z in sentences[i]]
        other=max((x for k,x in enumerate(comps) if k not in set(pos)),default=0)
        att=[]
        for k in pos:
            z=sentences[i][k]
            residual=z & terms
            left=frac(residual)
            exclusive=frac(residual-body[j])
            best_completion=max((frac((c|title[j])-z) for c in sentences[j]),default=0)
            att.append([left,exclusive,min(left,best_completion),left+best_completion,
                        frac(z)-other,frac((z|companion)&terms),left/math.sqrt(max(1,indeg[j]*outdeg[i]))])
        return [max(row[k] for row in att) for k in range(7)]
    pairs=list(itertools.combinations(range(n),2))
    X=[];W=[]; explain=[]
    for i,j in pairs:
        # Every scalar is either symmetric or pooled across the two directions.
        a,b=node[i],node[j]
        flat=meta+[v for x,y in zip(a,b) for v in (min(x,y),max(x,y))]
        flat.extend([frac(support[i]|support[j]),frac(support[i]&support[j]),
                     min(frac(support[i]-support[j]),frac(support[j]-support[i])),
                     frac(title[i]|title[j]),frac(title[i]&title[j])])
        li,lj=links.get((i,j),()),links.get((j,i),())
        g=[float(bool(li) or bool(lj)),float(bool(li) and bool(lj)),max(len(li),len(lj)),
           min(indeg[i],indeg[j]),max(indeg[i],indeg[j]),min(outdeg[i],outdeg[j]),max(outdeg[i],outdeg[j]),
           max((1/math.sqrt(max(1,indeg[t]*outdeg[s])) for s,t in ((i,j),(j,i)) if (s,t) in links),default=0.)]
        v=direction(i,j,False);rev=direction(j,i,False)
        sh=direction(i,j,True);sr=direction(j,i,True)
        def pooled(x,y):return [m for h,k in zip(x,y) for m in (max(h,k),min(h,k))]
        X.append(flat+g+pooled(v,rev))
        W.append(pooled(sh,sr))
        explain.append([list(li),list(lj)])
    return node,meta,bms,pairs,X,W,explain,len(links),sum(len(z) for z in links.values())

