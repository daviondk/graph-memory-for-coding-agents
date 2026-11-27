"""Recompute primary ranks using complete past observations and exact rational arithmetic."""
from collections import Counter,defaultdict
from fractions import Fraction
from collect import HERE,NAMES,load,save

def audit(name,rows,records):
    ids={};prior_events=[];occ=defaultdict(list);checks=0
    for t,(sha,input_paths) in enumerate(rows):
        valid=input_paths if len(input_paths)<=64 else []
        if t>=len(rows)//2 and len(valid)>=2:
            row=records[checks]
            anchor=valid[int(sha,16)%len(valid)]
            f=ids.get(anchor,-1)
            assert (t,sha,f)==(row["t"],row["sha"],row["anchor"])
            live={j for seq in occ.values() for j in seq[-8:]}
            options=[j for j in occ[f] if j in live]
            candidates={q for q in ids.values() if q!=f}
            freq=Counter(y for v in prior_events[-32:] for y in v)
            owned=sorted(occ[f][-8:],reverse=True)
            fill=sorted(options,key=lambda j:(len(prior_events[j])>6,-j))[:8]
            usable=min(sum(4*len(prior_events[j]) for j in js) for js in (owned,fill))
            assert usable==row["wire_budget"]==4*sum(len(prior_events[j]) for j in fill)
            for name,js in (("own_norm",owned),("fill6_norm",fill)):
                for limited in (False,True):
                    left=usable;chosen=[]
                    for j in js:
                        length=4*len(prior_events[j])
                        if limited and length>left:continue
                        chosen.append(j);left-=length
                    score=defaultdict(Fraction)
                    for j in chosen:
                        votes=Fraction(1,len(prior_events[j])-1)
                        for y in prior_events[j]:score[y]+=votes
                    ranked=sorted(candidates,key=lambda y:(-score[y],-freq[y],y))[:8]
                    actual=row["methods"][name+("_bytes" if limited else "")]
                    assert actual["events"]==chosen and actual["rank"]==ranked
                    hits=sum(p in ids and ids[p] in ranked for p in valid if p!=anchor)
                    assert hits==actual["hit_count"]
            checks+=1
        codes=[ids.setdefault(path,len(ids)) for path in valid]
        prior_events.append(codes)
        if len(codes)>=2:
            for y in codes:occ[y].append(t)
    assert checks==len(records)
    return checks

if __name__=="__main__":
    streams=load(HERE/"events.json.gz");records=load(HERE/"queries.json.gz")
    counts={name:audit(name,streams[name],records[name]) for name in NAMES}
    out=dict(queries=sum(counts.values()),policy_query_checks=sum(counts.values())*4,projects=counts)
    save(HERE/"ranking-audit.json",out)
    print(out)
