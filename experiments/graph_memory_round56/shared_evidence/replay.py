import argparse
from collections import Counter,defaultdict
from heapq import nlargest
from pathlib import Path
from statistics import fmean
import sys
from retain import HERE,Retained
sys.path.insert(0,str(HERE.parent/"event_intersection"))
from evaluate import panels,chosen
from run import load,save

def replay(repo,rows,panel,b):
    ids={};events=[];freq=Counter();all_inc=defaultdict(list)
    stores={p:Retained(b,p,repo) for p in ("last","hash")}
    out=[]
    for t,(rev,raw) in enumerate(rows):
        paths=raw if len(raw)<=64 else []
        name=chosen(panel,rev,t,len(rows),paths)
        if name is not None:
            a=ids.get(name,-1)
            target_ids={ids.get(p,-9) for p in paths if p!=name}
            pool=[i for i in range(len(ids)) if i!=a]
            truth=Counter(i for j in all_inc[a] for i in events[j])
            expect=nlargest(8,pool,key=lambda i:(truth[i],freq[i],-i))
            exact=[(i,truth[i]) for i in expect]
            info={}
            def assess(packet,work):
                return [sum(i in target_ids for i,v in packet),int([i for i,v in packet]==expect),
                        int(packet==exact),*work]
            info["full"]=assess(exact,[len(all_inc[a]),sum(len(events[j]) for j in all_inc[a])])
            cert={}
            for policy,mem in stores.items():
                packets,cost,p,lookups,missing=mem.read(a,pool,freq,truth)
                assert p==exact
                cert[policy]=[lookups,missing]
                for mode,packet in packets.items():
                    info[policy+"_"+mode]=assess(packet,cost[mode])
            out.append(dict(t=t,sha=rev,a=a,m=len(paths),methods=info,certificate=cert))
        codes=[ids.setdefault(s,len(ids)) for s in paths]
        events.append(codes)
        if t>=32:freq.subtract(events[t-32])
        freq.update(codes)
        for mem in stores.values():mem.ingest(codes,paths,rev,t)
        if len(codes)>=2:
            for i in codes:all_inc[i].append(t)
    physical={}
    for policy,mem in stores.items():
        physical[policy]=dict(distinct_retained=len(mem.events),total_events=mem.emitted,
                     admitted_member_entries=sum(map(len,mem.events.values())),owner_links=sum(mem.owners.values()),
                     visible_file_event_entries=sum(map(len,mem.incident.values())))
    return out,physical

def summary(rows):
    stats={}
    for name in rows[0]["methods"]:
        points=[r["methods"][name] for r in rows]
        stats[name]=dict(recall=fmean(a[0]/(r["m"]-1) for a,r in zip(points,rows)),
                         hit=sum(p[0]>0 for p in points),exact_ids=sum(p[1] for p in points),
                         exact_ids_scores=sum(p[2] for p in points),
                         decoded_events=sum(p[3] for p in points),decoded_members=sum(p[4] for p in points))
    cert={p:dict(complete_incidence=sum(r["certificate"][p][1]==0 for r in rows),
                 exact_no_archive=sum(r["certificate"][p][0]==0 for r in rows),
                 exact_pair_counts=sum(r["certificate"][p][0] for r in rows)) for p in ("last","hash")}
    return dict(n=len(rows),methods=stats,certificate=cert)

def main():
    p=argparse.ArgumentParser();p.add_argument("--verify",action="store_true");args=p.parse_args()
    totals={}
    for b in (8,2,4,16):
        for panel,repos in panels().items():
            by_repo={};stores={}
            for repo,stream in repos.items():
                by_repo[repo],stores[repo]=replay(repo,stream,panel,b)
            k=panel+str(b)
            agg=summary([r for rs in by_repo.values() for r in rs])
            totals[k]=dict(pooled=agg,projects={p:summary(rs) for p,rs in by_repo.items() if rs},stores=stores)
            dest=HERE/(k+"-queries.json.gz")
            if args.verify:assert load(dest)==by_repo
            else:save(dest,by_repo)
            print(k,agg["n"],[(m,round(s["recall"]*100,2)) for m,s in agg["methods"].items()],flush=True)
    if args.verify:assert load(HERE/"results.json")==totals
    else:save(HERE/"results.json",totals)
if __name__=="__main__":main()
