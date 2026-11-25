"""Portable selection of one context-expanding read from already visible source windows."""
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
import math
import re

WORDS=re.compile(r"[^\W_]+",re.UNICODE)

@dataclass(frozen=True)
class Window:
    field: object
    start: int
    end: int
    text: str
    tokens: int

def make_windows(fragments,tokenizer,window_tokens=128):
    """fragments is [(field, start_char, visible_text)] in delivery order."""
    windows=[]
    for field,start,text in fragments:
        offsets=tokenizer.encode(text,add_special_tokens=False).offsets
        if not offsets:
            windows.append(Window(field,start,start+len(text),text,0))
        for j in range(0,len(offsets),window_tokens):
            k=min(j+window_tokens,len(offsets))
            a=offsets[j][0] if j else 0
            b=offsets[k][0] if k<len(offsets) else len(text)
            windows.append(Window(field,start+a,start+b,text[a:b],k-j))
    return windows

def lexical_order(query,windows):
    words=set(WORDS.findall(query.casefold()))
    docs=[Counter(WORDS.findall(w.text.casefold())) for w in windows]
    avg=sum(map(lambda d:sum(d.values()),docs))/len(docs) if docs else 0
    avg=avg or 1
    idf={w:math.log1p((len(docs)-df+.5)/(df+.5)) for w in sorted(words) if (df:=sum(w in d for d in docs))}
    scores=[]
    for d in docs:
        norm=1.2*(.25+.75*sum(d.values())/avg)
        scores.append(sum(idf[w]*d[w]*2.2/(d[w]+norm) for w in sorted(words&d.keys())))
    return sorted(range(len(scores)),key=lambda j:(-scores[j],j))

def union_intervals(ranges):
    out=[]
    for l,h in sorted(ranges):
        if l>h:raise ValueError("reversed interval")
        if l==h:continue
        if out and out[-1][1]>=l:out[-1]=(out[-1][0],max(h,out[-1][1]))
        else:out.append((l,h))
    return out

def choose(windows,lex_order,visible,field_lengths,header_tokens,budget=256):
    """Return (policy -> window index or None, [(predicted_end, unseen_chars, predicted_width)]).
    visible is {field:[(l,h)]}; header_tokens is a nonnegative count per candidate.
    The reader sees no hidden field contents or labels.
    """
    n=len(windows)
    if sorted(lex_order)!=list(range(n)) or len(header_tokens)!=n:raise ValueError("window ranks/header counts")
    rank={j:i for i,j in enumerate(lex_order)}
    by={key:union_intervals(rs) for key,rs in visible.items()}
    details=[];values=[]
    for j,w in enumerate(windows):
        limit=field_lengths[w.field];h=header_tokens[j]
        if not (0<=w.start<=w.end<=limit and w.tokens>=0 and h>=0):raise ValueError("malformed window")
        available=max(0,budget-h);width=w.end-w.start
        chars=available*width//w.tokens if w.tokens else available
        right=min(limit,w.start+chars);total=right-w.start
        overlap=sum(max(0,min(right,b)-max(w.start,a)) for a,b in by.get(w.field,()))
        new=total-overlap
        if not 0<=new<=total:raise AssertionError("invalid novelty")
        details.append((right,new,total));values.append(Fraction(new,total) if total else Fraction(0))
    picks={"first":0 if n else None,"bm25":lex_order[0] if n else None,
           "first_positive":None,"max_novelty":None,"rank_novelty":None}
    valid=[j for j in lex_order if values[j]>0]
    if valid:
        picks["first_positive"]=valid[0]
        picks["max_novelty"]=max(valid,key=lambda j:(values[j],-j))
        picks["rank_novelty"]=max(valid,key=lambda j:(values[j]/(rank[j]+1),-rank[j],-j))
    return picks,details

