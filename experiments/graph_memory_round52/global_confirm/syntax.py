"""Freeze a dev-fitted question gate and apply fixed surface-coordination controls."""
from collections import Counter
import sys
import numpy as np
from panel import HERE, GP, DEV, S, read, save, hashfile, tokens

WORDS=["both","same","which","who","where","when","whose","earlier","first","later","more","older","younger"]
FEATURES=["has_conjunction","conjunctions_saturated",*WORDS,"question_length","title_length","content_count",
          "independent_candidates","single_candidate","rare_word_frequency"]
ARMS=["primary_href","primary_text","href_first","text_first","free","coord_question_only","coord_explicit",
      "coord_cautious","learned_dev","primary_free"]
def features(question, seedtitle, gate):
    q=tokens(question);seed=tokens(seedtitle)
    regions=[(i,i+len(seed)) for i in range(len(q)) if seed and q[i:i+len(seed)]==seed]
    covered={j for a,b in regions for j in range(a,b)}
    conj=sum(t in ("and","or") and j not in covered for j,t in enumerate(q))
    addr,n,lo,hi,terms,df=gate
    sat=lambda x:x/(1+x)
    v=[int(bool(conj)),sat(conj),*[int(w in q) for w in WORDS],len(q)/(len(q)+20),sat(hi-lo),sat(terms),
       sat(n),int(n==1),df/(df+59)]
    assert len(v)==len(FEATURES)
    return conj,v

def fit():
    from sklearn.linear_model import LogisticRegression
    from sklearn import __version__
    rows=read(GP/"predictions.json.gz");audit=read(GP/"graded-rows.json.gz")
    names=read(GP/"chosen-titles.json.gz");questions=read(DEV/"questions.json.gz")
    spec=read(GP/"prediction-seal.json")
    order=spec["arms"]
    xs=[];ys=[]
    for q,row in sorted(rows.items()):
        gate=row["gates"][1]
        if not gate[1]:continue
        a=audit[q][1]
        direct,href=a[order.index("primary_href")],a[order.index("href_first")]
        if direct==href:continue
        _,x=features(questions[q],names[str(row["seed"])][1],gate)
        xs.append(x);ys.append(direct)
    clf=LogisticRegression(C=1,max_iter=1000,tol=1e-9)
    clf.fit(xs,ys)
    assert clf.n_iter_[0]<1000
    model={"coef":clf.coef_[0].tolist(),"intercept":float(clf.intercept_[0]),"features":FEATURES,
           "train_dev_decisive":dict(Counter(ys)),"threshold":.5,"sklearn":__version__,
           "registration":hashfile(HERE/"PROTOCOL_RU.md"),"source_dev":hashfile(GP/"graded-rows.json.gz"),
           "feature_code":hashfile(HERE/"syntax.py")}
    save(HERE/"dev-model.json",model)
    print("dev model frozen",len(xs),dict(Counter(ys)))

def choose(question, seedtitle, gate, question_second, href, text, free, model):
    addr,count,*_=gate
    independent=bool(count)
    conj,x=features(question,seedtitle,gate)
    score=model["intercept"]+sum(v*w for v,w in zip(x,model["coef"]))
    choices=[addr if independent else href,addr if independent else text,href,text,free,
             question_second if conj else href,(addr if independent else question_second) if conj else href,
             addr if conj and independent else href,addr if independent and score>=0 else href,
             addr if independent else free]
    return choices, bool(conj), score>=0 and independent

if __name__=="__main__":fit()

