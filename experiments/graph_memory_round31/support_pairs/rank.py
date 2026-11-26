"""Rank all unordered document pairs without access to benchmark annotations."""
from collections import Counter
from itertools import combinations
from math import log
import hashlib,re
from prepare import ROOT,PRIVATE,get,put,sha
TOKEN=re.compile(r"[^\W_]+",re.UNICODE)
def words(s):return TOKEN.findall(s.lower())
def score(question,candidate_titles,texts):
    query=set(words(question));n=len(texts)
    contents=[words(" ".join(doc)) for doc in texts]; titles=[words(t) for t in candidate_titles]
    docs=[Counter(t+t+c) for t,c in zip(titles,contents)];lengths=[sum(d.values()) for d in docs]
    avg=sum(lengths)/max(n,1) or 1
    df=Counter(t for d in docs for t in d)
    idf={t:log(1+(n-v+0.5)/(v+0.5)) for t,v in df.items()}
    baseline=[sum(idf[t]*d[t]*2.2/(d[t]+1.2*(.25+.75*size/avg)) for t in sorted(query) if t in d) for d,size in zip(docs,lengths)]
    sets=[set(t) for t in contents];padded=[" "+" ".join(doc)+" " for doc in contents];phrases=[" "+" ".join(t)+" " for t in titles]
    def bridge(i,j):
        keys=set(titles[i]);w=sum(idf.get(t,0) for t in sorted(keys)) or 1
        return 3.0*int(len(phrases[i].strip())>=3 and phrases[i] in padded[j])+sum(idf.get(t,0) for t in sorted(keys&sets[j]))/w
    edges=list(combinations(range(n),2))
    additive={(i,j):baseline[i]+baseline[j] for i,j in edges}
    joint={(i,j):v+max(bridge(i,j),bridge(j,i)) for (i,j),v in additive.items()}
    # Tie by lexicographic node ID for additive matches ordered individual IDs.
    return {m:[list(e) for e in sorted(v,key=lambda e:(-v[e],e))] for m,v in (("add",additive),("joint",joint))},sorted(range(n),key=lambda i:(-baseline[i],i))
def main():
    path=PRIVATE/"blind.json.gz";source=get(ROOT/"source.json");assert sha(path)==source["observations"]
    cases=get(path);out={}
    for q,case in sorted(cases.items()):
        titles=case["titles"];seq=sorted(range(len(titles)),key=lambda i:hashlib.sha256((q+"|"+titles[i]).encode()).digest())
        assert len(titles)==len(set(titles))
        pred,individual=score(case["q"],[titles[i] for i in seq],[case["sentences"][i] for i in seq])
        out[q]={"order":seq,"pairs":pred,"docs":individual}
    put(ROOT/"rankings.json.gz",out);put(ROOT/"ranking-seal.json",{"rankings":sha(ROOT/"rankings.json.gz"),
          "protocol":sha(ROOT/"PROTOCOL_RU.md"),"code":sha(ROOT/"rank.py"),"source":sha(ROOT/"source.json"),"n":len(out)})
if __name__=="__main__":main()
