from collections import Counter,defaultdict
import hashlib,re,unicodedata
from rep_io import *
def norm(s):return " ".join(unicodedata.normalize("NFKC",s).casefold().split())
def title(a):return norm(a["title"].replace("_"," "))
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def body(a):return "\n\n".join(z["context"] for z in a["paragraphs"])
def meta(a):
    text=body(a);paragraphs={digest(n) for p in a["paragraphs"] if len(n:=norm(p["context"]))>=128}
    return title(a),digest(norm(text)),paragraphs
def qs(a):
    for p in a["paragraphs"]:
        for q in p["qas"]:yield q["id"],q["question"]
def main():
    freeze();assert sha(TRAIN)=="3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955"
    dev=read(DEV)["data"];train=read(TRAIN)["data"]
    dt=set();db=set();dp=set();di=set();dq=set()
    for a in dev:
        t,b,p=meta(a);dt.add(t);db.add(b);dp.update(p)
        for i,q in qs(a):di.add(i);dq.add(norm(q))
    acc_t=set();acc_b=set();acc_p=set();accepted=[];excluded={}
    for a in sorted(train,key=lambda z:(title(z),digest(norm(body(z))))):
        t,b,p=meta(a);issues=[]
        for key,truth in (("dev_title",t in dt),("dev_body",b in db),("dev_para",bool(p&dp)),("train_title",t in acc_t),("train_body",b in acc_b),("train_para",bool(p&acc_p))):
            if truth:issues.append(key)
        if issues:excluded[a["title"]]=issues;continue
        acc_t.add(t);acc_b.add(b);acc_p.update(p);accepted.append(a)
    groups=defaultdict(list);qi=set();qtxt=set();reasons=Counter();arr=[]
    for a in accepted:
        for i,q in qs(a):arr.append((digest("replication-v1/"+i),a["title"],i,norm(q)))
    for pr,t,i,q in sorted(arr):
        flags=[k for k,cond in (("dev_id",i in di),("dev_question",q in dq),("train_id",i in qi),("train_question",q in qtxt)) if cond]
        if flags:
            reasons.update(["|".join(flags)]);continue
        qi.add(i);qtxt.add(q);groups[t].append((pr,i))
    panel={a["title"]:{"ids":[i for h,i in groups[a["title"]][:12]],"body_sha":digest(body(a))} for a in accepted if groups[a["title"]]}
    assert all(len(rec["ids"])<=12 for rec in panel.values())
    out={"plan":sha(D/"plan.json"),"source":sha(TRAIN),"prior_dev":sha(DEV),"initial_articles":len(train),"dev_articles":len(dev),"accepted_articles":len(accepted),
      "excluded_articles":excluded,"filtered_questions":dict(reasons),"questions_in_accepted_articles":len(arr),"eligible_unique_questions":len(qi),"n":sum(len(z["ids"]) for z in panel.values()),"articles":len(panel),"panel":panel}
    p=D/"cohort.json.gz"
    if p.exists():assert read(p)==out
    else:save(p,out)
    print({k:v for k,v in out.items() if k not in ("panel","excluded_articles")},excluded)
if __name__=="__main__":main()
