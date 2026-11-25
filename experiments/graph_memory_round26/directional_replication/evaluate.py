from collections import Counter,defaultdict
from statistics import mean
import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from rep_io import *
def true_spans(keys):
    gold={};quality=Counter()
    for article in read(TRAIN)["data"]:
        off=0
        for p in article["paragraphs"]:
            text=p["context"]
            for q in p["qas"]:
                i=q["id"]
                if i not in keys:continue
                good=set();quality["selected_annotations"]+=len(q["answers"])
                for a in q["answers"]:
                    l=a["answer_start"];h=l+len(a["text"])
                    if not(0<=l<h<=len(text)) or text[l:h]!=a["text"]:
                        quality["misaligned_or_empty_annotations"]+=1;continue
                    good.add((off+l,off+h))
                if good:quality["usable_questions"]+=1
                else:quality["no_usable_gold"]+=1
                if len(good)>1:quality["multiple_usable_spans"]+=1
                assert i not in gold;gold[i]=sorted(good)
            off+=len(text)+2
    assert set(gold)==set(keys);return gold,dict(quality)
def annotate(base,op,valid):
    spans=sorted((l,h) for e,l,h in base if h>l)+[(r[1],r[2]) for r in op if r[2]>r[1]]
    united=[]
    for l,h in sorted(spans):
        if united and l<=united[-1][1]:united[-1][1]=max(h,united[-1][1])
        else:united.append([l,h])
    vals=[sum(max(0,min(h,b)-max(l,a)) for a,b in united)/(h-l) for l,h in valid]
    cov=max(vals);return [int(cov==1),cov,sum(v[3] for v in op),len(op),sum(v[6] for v in op)]
def resample(rows,group,diff,seed):
    gr=defaultdict(list)
    for r in rows:gr[r[group]].append(diff(r))
    ts=sorted(gr);tot=np.array([sum(gr[t]) for t in ts]);sizes=np.array([len(gr[t]) for t in ts])
    rng=np.random.default_rng(seed);g=len(ts);n=len(rows);boot=[]
    for _ in range(200):
        ix=rng.integers(0,g,(100,g));boot.extend(tot[ix].sum(axis=1)/sizes[ix].sum(axis=1))
    v=[diff(r) for r in rows];a=tot[tot!=0].astype("int64");obs=abs(int(a.sum()));cnt=Counter({0:1})
    if len(a)<=20:
        for val in a:
            nv=Counter()
            for s,m in cnt.items():nv[s+int(val)]+=m;nv[s-int(val)]+=m
            cnt=nv
        p=sum(m for x,m in cnt.items() if abs(x)>=obs)/2**len(a);kind="exact"
    else:
        exceed=0
        for _ in range(200):
            signs=rng.choice([-1,1],size=(500,len(a)));exceed+=sum(np.abs(signs@a)>=obs)
        p=(1+int(exceed))/100001;kind="monte_carlo_plus_one"
    return {"queries":n,"clusters":len(gr),"wins":sum(x>0 for x in v),"losses":sum(x<0 for x in v),"net":sum(v),"change_pp":100*mean(v),"cluster95_pp":(100*np.quantile(boot,[.025,.975])).tolist(),
      "nonzero_clusters":len(a),"article_positive":int(sum(tot>0)),"article_negative":int(sum(tot<0)),"two_sided_p":p,"sign_flip":kind}
def main():
    freeze();decisions={};opened={}
    for stage,target in (("choices",decisions),("read",opened)):
        seal=read(D/f"{stage}-lock.json");assert seal["plan"]==sha(D/"plan.json") and seal["cohort"]==sha(D/"cohort.json.gz")
        for n,h in seal["files"]:
            f=D/n;assert sha(f)==h
            chunk=read(f);assert not(set(target)&set(chunk));target.update(chunk)
    assert set(decisions)==set(opened);gt,quality=true_spans(decisions)
    rows=[]
    for q,d in sorted(decisions.items()):
        good=gt[q]
        if not good:continue
        r=opened[q];vals={k:annotate(d["base"],x,good) for k,x in r["arms"].items()}
        eq={k:[annotate(d["base"],x,good) for x in z] for k,z in r["equal"].items()}
        assert all(a[2]==b[2]<=256 for a,b in eq.values()) and d["before"]<=2048
        rows.append({"q":q,"t":d["t"],"base":annotate(d["base"],[],good)[0],"before_tokens":d["before"],"both_possible":bool(d["cut"] and d["cut"]["l"]>0),"vals":vals,"eq":eq})
    def table(panel):
        rv={}
        for k in panel[0]["vals"]:
            vals=[r["vals"][k] for r in panel];rv[k]={"hits":sum(z[0] for z in vals),"coverage":mean(z[1] for z in vals),"real_tokens":mean(z[2] for z in vals),"two_headers":sum(z[3]==2 for z in vals),"header_tokens":mean(z[4] for z in vals)}
        return rv
    eqres={}
    for k in rows[0]["eq"]:
        zs=[r["eq"][k] for r in rows];eqres[k]={"hits":[sum(z[j][0] for z in zs) for j in (0,1)],"coverage":[mean(z[j][1] for z in zs) for j in (0,1)],"mean_tokens":mean(z[0][2] for z in zs),"exact_cost":sum(z[0][2]==z[1][2] for z in zs)}
    eligible=[r for r in rows if r["both_possible"]];delta=lambda r:r["eq"]["both-right"][0][0]-r["eq"]["both-right"][1][0]
    dig=save(D/"per-query.json.gz",rows)
    out={"protocol":sha(D/"plan.json"),"read_seal":sha(D/"read-lock.json"),"cohort":sha(D/"cohort.json.gz"),"n":len(rows),"initial":sum(r["base"] for r in rows),"before_tokens":mean(r["before_tokens"] for r in rows),"quality":quality,"observed":table(rows),"common_cost":eqres,"both_possible":len(eligible),"selected_articles":len({r["t"] for r in rows}),"primary":resample(rows,"t",delta,263117),
         "both_possible_primary":resample(eligible,"t",delta,263117),"both_possible_methods":table(eligible),"full_budget":resample(rows,"t",lambda r:r["vals"]["both"][0]-r["vals"]["right"][0],263117),"reference_feasible_left_common_cost":resample(rows,"t",lambda r:r["eq"]["both-feasible_left"][0][0]-r["eq"]["both-feasible_left"][1][0],263117),"per_query":dig}
    save(D/"results.json",out);print(out)
if __name__=="__main__":main()
