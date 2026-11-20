"""Role-sensitive alignment of compound identifiers. No target or corpus state."""
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

import numpy as np

WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
PART = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
DECL = re.compile(r"\b(class|interface|enum|record|def|trait|object)\s+([A-Za-z_]\w*)")
METHOD = re.compile(r"(?:^|\s)([A-Za-z_]\w*)\s*\([^()]*\)\s*(?:throws\b[^;{]*)?[{:;]?\s*$")
IGNORE = set("""a an or the of new is as in self this cls get set on if do map var for and by else return
from public static final private protected synchronized void def class abstract null none true false
int bool boolean float double long short char string object str throws throw interface continue while
try catch with import package pass super override to it that which""".split())

@lru_cache(40000)
def terms(word):
    return frozenset(x.lower() for x in PART.findall(word) if len(x) > 1 and x.lower() not in IGNORE)

def split_words(words):
    return frozenset(t for word in words for t in terms(word))

@lru_cache(800)
def index(doc):
    source = doc.splitlines()
    bounded = source if len(source) <= 180 else source[:135] + source[-45:]
    roots = []
    members = []
    types = []
    for line in bounded:
        m = DECL.search(line)
        if m:
            roots.append(m[2])
            members.append(m[2])
            types.append(m[1])
        elif '(' in line:
            m = METHOD.search(line.strip())
            if m and m[1].lower() not in IGNORE:
                members.append(m[1])
    root = roots[0] if roots else (members[0] if members else '')
    body_words = WORD.findall('\n'.join(bounded))
    raw = frozenset(x for x in body_words if x and x[0].isupper())
    return (root, terms(root), split_words(members), split_words(body_words), raw,
            len(set(members)), types[0] if types else '', len(roots))

def make(code, docs):
    nodes = [index(doc) for doc in docs]
    n = len(nodes)
    lines = code.splitlines()
    q = split_words(WORD.findall(code))
    suffix = split_words(WORD.findall(lines[-1] if lines else ''))
    accesses = split_words(re.findall(r"[.]\s*([A-Za-z_]\w*)", code))
    compounds = [terms(w) for w in WORD.findall(code) if terms(w)]
    fields = (1, 2, 3)
    freq = [Counter(t for v in nodes for t in v[j]) for j in fields]
    direct = []
    for node in nodes:
        root, rp, mp, bp, cap, nm, kind, nr = node
        row = [math.log1p(nm), len(rp), math.log1p(nr), int(kind=='class'),
               int(kind=='def'), int(kind=='interface'), int(kind=='enum'),
               float(root[:1].isupper()), float(bool(root) and root.isupper())]
        for field, df in zip((rp, mp, bp),freq):
            for query in (q, suffix, accesses):
                overlap = query & field
                weight = sum(math.log((n+1)/(df[t]+.5)) for t in sorted(overlap))
                row.extend([len(overlap)/max(len(field),1), weight/max(len(query),1),
                            max((math.log((n+1)/(df[t]+.5)) for t in overlap),default=0.)])
        align = [len(c & rp)/max(1,len(c | rp)) for c in compounds]
        row.extend([max(align,default=0.),sum(align)/max(1,len(align)),
                    max((a/(1+.15*d) for d,a in enumerate(reversed(align))),default=0.),
                    float(bool(rp) and rp<=q),float(bool(rp) and rp<=suffix)])
        direct.append(row)
    direct = np.asarray(direct, dtype=np.float32)
    # A reference to the uppercase type is supported by the source node's own field match.
    root_ids = defaultdict(list)
    for i, (name,*_) in enumerate(nodes):
        if name and name[:1].isupper():
            root_ids[name].append(i)
    incoming = [[] for _ in nodes]
    outgoing = [[] for _ in nodes]
    for i,node in enumerate(nodes):
        for name in sorted(node[4] & root_ids.keys()):
            for j in root_ids[name]:
                if j != i:
                    incoming[j].append((i,1/len(root_ids[name])))
                    outgoing[i].append((j,1/len(root_ids[name])))
    signals = direct[:,[10,19,28,36]]
    links = []
    for inc,out in zip(incoming,outgoing):
        row=[]
        for neigh in (inc,out):
            if neigh:
                values=np.asarray([signals[j]*w for j,w in neigh])
                row.extend(values.max(0))
                row.extend(values.mean(0))
            else:
                row.extend([0.]*8)
        links.append(row)
    return direct, np.asarray(links,dtype=np.float32)
