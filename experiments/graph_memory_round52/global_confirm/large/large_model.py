"""Shallow supervised gate fit only on the same decisive dev examples as the frozen logit."""
from large_panel import HERE,CONF,S,DEV,GP,read,save,hashfile,tokens
from syntax import FEATURES,features

def surface(question,seedtitle):
    words=tokens(question);seed=tokens(seedtitle)
    starts=[i for i in range(len(words)) if seed and words[i:i+len(seed)]==seed]
    mask={t for i in starts for t in range(i,i+len(seed))}
    other=[t for i,t in enumerate(words) if i not in mask]
    coord=any(t in ("and","or") for t in other)
    same=False;found=False
    for t in other:
        if t=="same":found=True
        if t=="as" and found:same=True
    return coord or same

def fit():
    import numpy as np
    import sklearn
    from sklearn.tree import DecisionTreeClassifier,export_text
    rows=read(GP/"predictions.json.gz");audit=read(GP/"graded-rows.json.gz")
    names=read(GP/"chosen-titles.json.gz");qtext=read(DEV/"questions.json.gz")
    arms=read(GP/"prediction-seal.json")["arms"]
    X=[];Y=[]
    for q,r in sorted(rows.items()):
        g=r["gates"][1];v=audit[q][1]
        y=v[arms.index("primary_href")];base=v[arms.index("href_first")]
        if g[1] and y!=base:
            _,x=features(qtext[q],names[str(r["seed"])][1],g)
            X.append(x);Y.append(y)
    clf=DecisionTreeClassifier(max_depth=3,min_samples_leaf=20,criterion="gini",random_state=520117)
    clf.fit(X,Y)
    tree=clf.tree_
    payload={"feature":tree.feature.tolist(),"threshold":tree.threshold.tolist(),"left":tree.children_left.tolist(),
             "right":tree.children_right.tolist(),"predict":clf.classes_[tree.value[:,0,:].argmax(1)].tolist(),
             "samples":tree.n_node_samples.tolist(),"features":FEATURES,"sklearn":sklearn.__version__,"decisive":len(X),
             "pseudo":export_text(clf,feature_names=FEATURES),"frozen_linear":hashfile(CONF/"dev-model.json"),
             "code":hashfile(HERE/"large_model.py"),"protocol":hashfile(HERE/"PROTOCOL_RU.md")}
    assert all(predict(x,payload)==v for x,v in zip(X,clf.predict(X))) and len(X)==3076
    save(HERE/"dev-tree.json",payload)
    print(payload["pseudo"])

def predict(x,tree):
    leaf=0
    while tree["left"][leaf]!=-1:
        leaf=tree["left"][leaf] if x[tree["feature"][leaf]]<=tree["threshold"][leaf] else tree["right"][leaf]
    return tree["predict"][leaf]

if __name__=="__main__":fit()

