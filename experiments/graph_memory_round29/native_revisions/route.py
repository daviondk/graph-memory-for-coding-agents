"""Select refreshes using the old answer and observable version differences."""
from collections import Counter
from difflib import SequenceMatcher
import gzip,json,re
import numpy as np
from fetch import ROOT,CACHE,checksum,save
from prepare import hashkey
TOKEN=re.compile(r"\w+|[^\w\s]",re.UNICODE)
REL=set("more less increase decreases decreases increased higher lower greater smaller few fewer larger smaller most least longer shorter better worse fastest slower strongest no not never without cannot before after opposite faster stronger weaker different same".split())
def split(s):return [m.group().casefold() for m in TOKEN.finditer(s)]
def occurrences(hay,needle):
    if not needle:return []
    return [i for i in range(len(hay)-len(needle)+1) if hay[i:i+len(needle)]==needle]
def features(row):
    old,new,ans=row["old"],row["new"],row["prediction"];answer=split(ans)
    qwords={t for t in split(old[2]) if len(t)>2};basic=[];advanced=[]
    total_edits=0;old_count=visible_count=0;tentative=[];fully_aligned=True
    for source,target in zip(old,new):
        original,edited=split(source),split(target);positions=occurrences(original,answer);remaining=occurrences(edited,answer)
        ops=[op for op in SequenceMatcher(None,original,edited,autojunk=False).get_opcodes() if op[0]!="equal"]
        old_count+=len(positions);visible_count+=len(remaining)
        deleted=sum(b-a for _,a,b,_,_ in ops);inserted=sum(d-c for _,_,_,c,d in ops);total_edits+=deleted+inserted
        basic.extend([int(bool(ops)),len(ops),deleted,inserted,(deleted+inserted)/max(1,len(original)+len(edited)),len(positions),len(remaining)])
        changed={t for _,a,b,c,d in ops for t in original[a:b]+edited[c:d]}
        dist=min((max(a-(i+len(answer)),i-b,0) for _,a,b,c,d in ops for i in positions),default=10**4)
        advanced.extend([np.log1p(dist),len(changed&qwords),len(changed&set(answer)),len(changed&REL),
                         int(any(t.isdecimal() for t in changed)),int(any(a<=i<b or i<=a<i+len(answer) for _,a,b,c,d in ops for i in positions))])
        matches=list(TOKEN.finditer(target))
        for i in positions:
            replacements=[target[matches[c].start():matches[d-1].end()] for kind,a,b,c,d in ops if kind=="replace" and a==i and b==i+len(answer) and 0<d-c<=8]
            if len(replacements)==1:tentative.append(replacements[0])
            else:fully_aligned=False
    patch=tentative[0] if tentative and fully_aligned and len({s.casefold() for s in tentative})==1 and visible_count==0 else ans
    return basic+[len(answer)],advanced,total_edits,int(old_count>0 and visible_count==0),patch
def main():
    directory=CACHE.parent/"projected";lock=json.loads((ROOT/"inputs.json").read_bytes())
    def load(name):
        p=directory/(name+".json.gz");assert checksum(p)==lock[name];return json.loads(gzip.decompress(p.read_bytes()))
    view=load("blind");training=load("training");assert set(training)=={q for q,r in view.items() if r["training"]}
    featureset={q:features(v) for q,v in view.items()};train=sorted(training);test=sorted(set(view)-set(train))
    ranked={"random":{q:0 for q in test},"size":{q:featureset[q][2] for q in test},"missing":{q:featureset[q][3] for q in test}};fits={}
    for policy in ("basic","local"):
        def mat(ids):return np.asarray([featureset[q][0]+(featureset[q][1] if policy=="local" else []) for q in ids],dtype=np.float64)
        x=mat(train);y=np.asarray([training[q] for q in train]);mu=x.mean(axis=0);sd=x.std(axis=0);sd[sd<1e-8]=1
        x=(x-mu)/sd;offset=y.mean();beta=np.linalg.solve(x.T@x+20*np.eye(x.shape[1]),x.T@(y-offset))
        ranked[policy]=dict(zip(test,(offset+(mat(test)-mu)/sd@beta).tolist()))
        fits[policy]={"intercept":offset,"beta":beta.tolist(),"mean":mu.tolist(),"sd":sd.tolist()}
    schedule={}
    for method,values in ranked.items():
        order=sorted(test,key=lambda q:(-values[q],hashkey("ropes-routes-v1/"+q)))
        schedule[method]={q:idx for idx,q in enumerate(order)}
    info={q:{"group":view[q]["group"],"rank":{m:r[q] for m,r in schedule.items()},"patch":featureset[q][4],
             "patch_changed":featureset[q][4]!=view[q]["prediction"],"different_fields":[a!=b for a,b in zip(view[q]["old"],view[q]["new"])]} for q in test}
    (ROOT/"routes.json.gz").write_bytes(gzip.compress(json.dumps(info,sort_keys=True).encode(),mtime=0))
    save("route-seal.json",{"routes":checksum(ROOT/"routes.json.gz"),"inputs":checksum(ROOT/"inputs.json"),
                            "algorithm":checksum(ROOT/"route.py"),"fit":fits,"test_n":len(test)})
if __name__=="__main__":main()
