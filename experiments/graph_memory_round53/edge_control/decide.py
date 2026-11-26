"""Fit only against observed href labels on old 2Wiki, then seal all test selections."""
from array import array
from bisect import bisect_left
from collections import Counter
import math
import numpy as np
from setup import *
import re
import unicodedata
FEATURES=["early_position","span_width","occurrences","log_bm25","bm25_rr"]
ARMS=["real_salience","text_salience","real_top","text_top","text_proxy","real_random","text_random","real_original","text_original"]
def tokens(t):return re.findall(r"[^\W_]+",unicodedata.normalize("NFKC",t).lower())
def stream(p):
    with gzip.open(WORK/(p+".tsv.gz"),"rt",encoding="ascii") as f:
        for line in f:
            q,*items=line.rstrip("\n").split("\t");rs=[]
            for raw in items:
                i,page,b,pos,width,n,href=raw.split(",")
                rs.append((int(i),int(page),float(b),int(pos),int(width),int(n),int(href)))
            yield q,sorted(rs,key=lambda t:(-t[2],t[1],t[0]))
def feature(pos,w,n,b,j):return [16/(16+pos),min(w,8)/8,n/(1+n),math.log1p(max(b,0))/6,1/(1+j)]
def fit():
    from sklearn.linear_model import LogisticRegression
    import sklearn
    xs=array("d");ys=array("B");sw=array("d");qs=0
    for q,items in stream("dev"):
        li=[r for r in items if r[5]]
        if not li:continue
        qs+=1
        for j,(_,_,b,pos,w,n,h) in enumerate(li):
            xs.extend(feature(pos,w,n,b,j));ys.append(h);sw.append(1/len(li))
    x=np.frombuffer(xs,dtype=np.float64).reshape(-1,len(FEATURES));y=np.frombuffer(ys,dtype=np.uint8);w=np.frombuffer(sw,dtype=np.float64)
    clf=LogisticRegression(C=1,max_iter=300,tol=1e-8).fit(x,y,sample_weight=w)
    assert clf.n_iter_[0]<300
    return dict(coef=clf.coef_[0].tolist(),intercept=float(clf.intercept_[0]),train_rows=len(y),positives=int(y.sum()),train_questions=qs,
                features=FEATURES,sklearn=sklearn.__version__,target="address present among verified visible href targets, not QA annotations")
def salience(pool,info,k):
    pos=sorted(t[0] for t in info);width=sorted(-t[1] for t in info)
    keys=[(1/(1+min(j,4))+1/(1+bisect_left(pos,t[0]))+1/(1+bisect_left(width,-t[1])),-j,j) for j,t in enumerate(info)]
    return pool[min(v[2] for v in sorted(keys,reverse=True)[:k])][0]
def proxy(li,model,k):
    rank=sorted(range(len(li)),key=lambda j:(-sum(w*v for w,v in zip(model["coef"],feature(li[j][3],li[j][4],li[j][5],li[j][2],j))),j))
    return li[min(rank[:k])][0]
def read_base(source):
    ans={}
    for line in (source/"second.tsv").read_text().splitlines():
        q,*vals=line.split("\t");s,b,raw,tx,hr,uni,l,h,_,nl,nh,_=map(int,vals)
        ans[q]=(s,b,l,h,nl,nh)
    return ans
def apply(p,model):
    src,source=SPLITS[p];old=read(src/"predictions.json.gz");seal=read(src/"prediction-seal.json");arms=seal["arms"]
    source_rows=read_base(source);op=read(source/"opened.json.gz");result={};need=set()
    assert sha(source/"second.tsv")==seal["cache"]["second.tsv"] and sha(source/"opened.json.gz")==seal["cache"]["opened.json.gz"]
    for q,rs in stream(p):
        r=old[q];seed,base,old_l,old_h,nl,nh=source_rows[q];assert seed==r["seed"]
        addr=r.get("direct_gate",r.get("gate"))[0]
        h=[v for v in rs if v[6]];li=[v for v in rs if v[5]];k=min(len(h),len(li))
        assert len(h)==nh and len(li)==nl and (h[0][0] if h else base)==old_h and (li[0][0] if li else base)==old_l
        orig_h=addr if addr>=0 else old_h;orig_l=addr if addr>=0 else old_l
        assert orig_h==r["choices"][arms.index("primary_href")] and orig_l==r["choices"][arms.index("primary_text")]
        if addr>=0 or not k:
            fixed=addr if addr>=0 else base
            choices=[fixed]*5
            rh=rl=[fixed]
        else:
            observed=op[str(seed)];snippet=observed["prefix"]
            hinfo=[]
            for i,*_ in h:
                lo,hi,anchor,*_=min(observed["links"][str(i)],key=lambda v:(v[0],v[1]))
                assert snippet[lo:hi]==anchor
                hinfo.append((len(tokens(snippet[:lo])),len(tokens(anchor))))
            choices=[salience(h,hinfo,k),salience(li,[(v[3],v[4]) for v in li],k),h[0][0],li[0][0],proxy(li,model,k)]
            rh=[v[0] for v in h];rl=[v[0] for v in li]
        overlap=len({v[0] for v in h}&{v[0] for v in li})
        result[q]=dict(seed=seed,direct=addr>=0,base=base,sizes=[nh,nl,k,overlap],fixed=choices+[orig_h,orig_l],random=[rh,rl])
        need.update([seed,*choices,orig_h,orig_l,*rh,*rl])
    assert set(old)==set(result)
    return result,need
def main():
    reg=read(D/"registration.json");assert reg["protocol"]==sha(D/"PROTOCOL_RU.md")
    model=fit();save(D/"model.json",model)
    need=set()
    for p in ("hotpot","2wiki"):
        z,ids=apply(p,model);need.update(ids);save(D/(p+"-choices.json.gz"),z);print("FROZEN",p,len(z),flush=True)
    names={}
    with (DEV/"titles.txt").open(encoding="utf8") as f:
        for i,line in enumerate(f):
            if i in need:names[i]=line.rstrip("\n").split("\t",1)[1]
    assert len(names)==len(need)
    save(D/"titles.json.gz",names)
    files=["registration.json","PROTOCOL_RU.md","dump.cpp","setup.py","decide.py","model.json","hotpot-choices.json.gz","2wiki-choices.json.gz","titles.json.gz"]
    save(D/"prediction-seal.json",dict(arms=ARMS,fixed=ARMS[:5]+ARMS[-2:],files={n:sha(D/n) for n in files},
        gold_access="No QA labels used in candidate export, fit or decisions.",dump_hash={p:sha(WORK/(p+".tsv.gz")) for p in SPLITS}))
if __name__=="__main__":main()
