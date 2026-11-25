from factor import D,app,save,load,sha,np
rd=app.rd
from collections import defaultdict
from statistics import mean
import sys
sys.path.insert(0,str(app.OLD/"tail_read"))
from tail import compare,independent,pilot,OFF
def score(co):
    seal=load(D/(co+"-seal.json"));assert seal["code"]==sha(D/"factor.py")
    gold=load(OFF/"gold-spans.json.gz");arms=defaultdict(dict)
    for i,(n,h) in enumerate(sorted(seal["files"].items())):
        assert sha(D/n)==h
        ref={r["q"]:r for r in load(rd.source("dense",i))}
        for r in load(D/n):
            q=r["q"];rr=ref[q]["rr"];nodes=[pilot.RankedNodeRecord.model_validate(v) for v in rr];gs=tuple(pilot.SourceSpan.model_validate(v) for v in gold[q])
            for a,rank in r["ranks"].items():
                assert sorted(rank)==list(range(len(rr)))
                for pol in ("prefix","skip"):
                    keep=[];left=2048
                    for j in rank:
                        cost=nodes[j].token_count
                        if cost<=left:keep.append(j);left-=cost
                        elif pol=="prefix":break
                    if a=="dense":assert [rr[j]["node_id"] for j in keep]==ref[q]["arms"][pol]
                    m=pilot.span_metrics_under_token_budget(tuple(nodes[j] for j in keep),gs,2048)
                    alt=independent(gold[q],[rr[j] for j in keep]);assert all(abs(v-getattr(m,k))<1e-12 for v,k in zip(alt,("coverage","density","full_support"),strict=True))
                    key=pol+"/"+a;assert q not in arms[key]
                    arms[key][q]={"t":r["t"],"tokens":2048-left,**{k:getattr(m,k) for k in ("coverage","density","full_support","f1")}}
    assert all(set(rows)==set(gold) for rows in arms.values())
    stats={k:{"hits":sum(v["full_support"] for v in rs.values()),**{a:mean(v[a] for v in rs.values()) for a in ("full_support","coverage","density","tokens")}} for k,rs in arms.items()}
    pairs={}
    for pol in ("prefix","skip"):
        for a,b in (("factor","dense"),("factor","shape"),("factor","degree"),("factor","sham"),("factor","joint"),("rank","dense"),("shape","dense"),("degree","dense")):
            pairs[pol+"/"+a+"-"+b]=compare(arms[pol+"/"+a],arms[pol+"/"+b])
    save(D/(co+"-results.json"),{"summary":stats,"pairs":pairs});save(D/(co+"-outcomes.json.gz"),arms)
    print(co,{k:v["hits"] for k,v in stats.items()},flush=True)
if __name__=="__main__":score(sys.argv[1])
