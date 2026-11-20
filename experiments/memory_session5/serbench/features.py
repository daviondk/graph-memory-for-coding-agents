"""Label-blind feature extraction; no candidate positions or ID spellings in features."""
import hashlib, math, re, sys
from collections import Counter
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'upstream/src'))
from serbench import baseline

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def terms(obj):
    if isinstance(obj,list):return sum((terms(x) for x in obj),[])
    if not isinstance(obj,str):return []
    return re.findall(r"[a-z0-9]+",re.sub(r"([a-z])([A-Z])",r"\1 \2",obj).lower().replace("_"," "))
def putative_paths(x):
    if isinstance(x,list):return set(p for z in x for p in putative_paths(z))
    if not isinstance(x,str):return set()
    return set(re.findall(r"[\w./-]+\.[A-Za-z][\w]*",x.lower()))

class State:
    def __init__(self,row):
        self.sid=row['state_id'];self.repo=row['repo']
        self.issue=row['instance_id'];cs=sorted(row['candidate_evidence'],key=lambda c:digest(self.sid+'|'+c['evidence_id']))
        self.ids=[c['evidence_id'] for c in cs]
        self.visible=set(row.get('observed_evidence_ids',[]))
        self.eligible=[i for i,k in enumerate(self.ids) if k not in self.visible]
        docs=[baseline._candidate_text(c) for c in cs];bm=baseline._bm25_scores(baseline._query(row),docs)
        self.starter=sorted(range(len(cs)),key=lambda i:(-bm[i],self.ids[i]))[:8]
        paths=[str(c.get('source_path') or '').lower().replace('\\','/') for c in cs]
        self.paths=paths;self.dirs=[p.rpartition('/')[0] for p in paths];self.lines=[float(c.get('line_start') or 0) for c in cs]
        ts=[set(terms(c.get('content_excerpt'))) for c in cs];self.ts=ts
        df=Counter(term for doc in ts for term in doc);idf={t:math.log1p((len(cs)-f+.5)/(f+.5)) for t,f in df.items()}
        fields=['issue','information_need','current_observation','current_hypothesis','current_subgoal','opened_files','search_queries']
        queries=[set(terms(row.get(f))) for f in fields]
        file_refs=[putative_paths(row.get(f)) for f in fields]
        self.x=[]
        for i,c in enumerate(cs):
            p=paths[i];bn=p.rsplit('/',1)[-1];pt=set(terms(p));doc=ts[i]
            x=[math.log1p(bm[i]),math.log1p(len(docs[i])),math.log1p(len(doc)),math.log1p(len(pt))]
            for q,fr in zip(queries,file_refs):
                intersect=q & doc
                x.extend((math.log1p(sum(idf.get(t,0) for t in sorted(intersect))),len(intersect)/max(1,len(q)),
                          len(pt&q)/max(1,len(pt)),float(bool(p and (p in fr or any(z.endswith('/'+bn) or z==bn for z in fr))))))
            self.x.append(x)
        self.x=np.array(self.x)
        self.text=ts
    def pair(self,i,j):
        p,q=self.paths[i],self.paths[j];d,e=self.dirs[i],self.dirs[j]
        t,u=self.text[i],self.text[j];common=len(t&u)
        same=bool(p and p==q)
        return [float(same),float(bool(d and d==e)),float(p.rsplit('.',1)[-1]==q.rsplit('.',1)[-1]),
                1/(1+abs(self.lines[i]-self.lines[j])/100) if same else 0.,common/max(1,len(t)+len(u)-common),
                common/max(1,min(len(t),len(u))),len(set(p.split('/'))&set(q.split('/')))/max(1,len(set(p.split('/'))|set(q.split('/'))))]
