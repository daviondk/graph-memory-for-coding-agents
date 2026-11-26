"""Count operationally distinct forms of support/candidate overlap on the fixed panel."""
from collections import Counter,defaultdict
from itertools import combinations
import numpy as np
from join import D,R39,db,read,save


def counts(q,trace,reader):
    memberships=defaultdict(set)
    for i,s in reader.execute("select id,source from span where q=?",(q,)):
        memberships[i].add(s)
    sstep=dict(trace["sources"])
    start={i:max(sstep[s] for s in sources) for i,sources in memberships.items()}
    out=Counter(trajectories=1)
    visited=set()
    old_packet=[]
    for j,(_e,_m,updates,new_packet) in enumerate(trace["steps"],1):
        changed={a for a,_,_ in updates}
        out["groups"]+=1;out["changed"]+=bool(changed);out["joint"]+=len(changed)>=2
        out["producer_updates"]+=len(changed);out["pair_visits"]+=len(changed)*(len(changed)-1)//2
        kinds={a:1 if y>x else -1 for a,x,y in updates}
        hits={}
        for step,ids,suffix in ((j-1,old_packet,"before"),(j,new_packet,"after")):
            eligible={s for i,sp in memberships.items() if start[i]<=step for s in sp}
            selected={s for i in ids for s in memberships[i]}
            n=Counter()
            category={}
            for a in changed:
                f,time,args,call=trace["producers"][a]
                ok=f in eligible;arg=args in eligible
                assert not ok or time<=step
                n["visible"]+=time<=step
                n["exact"]+=ok
                n["selected"]+=f in selected
                n["arg_only"]+=arg and not ok
                n["neither"]+=not (arg or ok)
                n["both_fields"]+=arg and ok
                category[a]=(ok,f in selected)
            for name in ("visible","exact","selected","arg_only","neither","both_fields"):
                v=n[name];out[name+"_source_"+suffix]+=v
                if name in {"visible","exact","selected"}:
                    out[name+"_"+suffix]+=int(v>=2)
                    out[name+"_pairs_"+suffix]+=v*(v-1)//2
            if suffix=="before":
                for a,b in combinations(sorted(changed),2):
                    if category[a][0] and category[b][0]:
                        out["pair_plusplus" if kinds[a]==kinds[b]==1 else "pair_minusminus" if kinds[a]==kinds[b]==-1 else "pair_opposite"]+=1
                        out["repeat_pair_visits"]+=int((a,b) in visited)
                        visited.add((a,b))
            hits[suffix]={a for a,z in category.items() if z[1]}
        persist=hits["before"]&hits["after"]
        out["same_two_in_both"]+=len(persist)>=2
        out["same_pair_visits_in_both"]+=len(persist)*(len(persist)-1)//2
        out["joint_packet_changed_by_availability"]+=len(changed)>=2 and old_packet!=new_packet
        old_packet=new_packet
    for name in ("joint","exact_before","exact_after","selected_before","selected_after"):
        out["trajectory_"+name]=int(out[name]>0)
    return dict(out)


def main():
    qs=read(D/"projection.json.gz")["queries"];reader=db(R39/"reader.sqlite")
    rows={q:counts(q,tr,reader) for q,tr in sorted(qs.items())}
    total=Counter()
    for item in rows.values():total.update(item)
    rng=np.random.default_rng(48017);n=len(rows)
    boot=rng.integers(0,n,(10000,n));intervals={}
    contrasts=[("joint","groups"),("changed","groups"),("same_two_in_both","joint"),
               ("same_pair_visits_in_both","pair_visits"),("repeat_pair_visits","pair_visits"),
               ("joint_packet_changed_by_availability","joint"),("exact_pairs_before","pair_visits"),
               ("exact_pairs_after","pair_visits"),("selected_pairs_before","pair_visits"),
               ("selected_pairs_after","pair_visits")]
    for what in ("visible","exact","selected"):
        for when in ("before","after"):
            contrasts.extend([(what+"_"+when,"joint"),(what+"_"+when,"groups"),
                              (what+"_source_"+when,"producer_updates")])
    for what in ("joint","exact_before","exact_after","selected_before","selected_after"):
        contrasts.append(("trajectory_"+what,"trajectories"))
    for num,den in contrasts:
        a=np.array([r.get(num,0) for r in rows.values()]);b=np.array([r.get(den,0) for r in rows.values()])
        ns=a[boot].sum(1);ds=b[boot].sum(1)
        ci=np.quantile(ns[ds>0]/ds[ds>0],[.025,.975]).tolist()
        intervals[num+"/"+den]=dict(n=int(a.sum()),den=int(b.sum()),ratio=float(a.sum()/b.sum()),ci95=ci,reps=int((ds>0).sum()))
    save("results.json",dict(trajectories=rows,total=dict(total),ratios=intervals))
    print(dict(total))

if __name__=="__main__":main()
