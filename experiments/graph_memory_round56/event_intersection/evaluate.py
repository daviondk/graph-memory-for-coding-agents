import argparse
from collections import Counter
import gzip
from pathlib import Path
import json
import struct
from statistics import fmean

from event_bounds import EpisodeState,HERE,lookup
from run import inputs,load,save

def panels():
    output=inputs()
    output["long"]=load(HERE/"long-events.json.gz")
    return output

def chosen(panel,rev,t,n_commits,paths):
    sha=int(rev,16)
    if panel=="long":
        return paths[(sha//11)%len(paths)] if t>=n_commits//2 and sha%11==0 and len(paths)>=2 else None
    return paths[sha%len(paths)] if t>=64 and len(paths)>=2 else None

def inventory(state):
    end=len(state.members)
    return dict(memberships=state.writes,edges_written_directed=sum(len(x)*(len(x)-1) for x in state.members),
                synopsis_bytes=sum(4+4*len(s) for s in state.recent.values()),
                postings_packed_bytes=sum(4+4*len(s) for s in state.all.values()),
                bitset_dense_bytes=(4+(end+7)//8)*len(state.count),
                bitset_trimmed_bytes=sum(4+(v.bit_length()+7)//8 for v in state.bitset.values()),
                files_with_events=len(state.count),episodes=end)

def replay(rows,panel,budget):
    state=EpisodeState(budget)
    ids={};events=[];freq=Counter();results=[]
    for t,(rev,allpaths) in enumerate(rows):
        paths=allpaths if len(allpaths)<=64 else []
        a=chosen(panel,rev,t,len(rows),paths)
        if a is not None:
            aid=ids.get(a,-1)
            pool=[i for i in range(len(ids)) if i!=aid]
            bits=state.bitset.get(aid,0)
            exact={i:(bits & state.bitset.get(i,0)).bit_count() for i in pool}
            expected=sorted(pool,key=lambda i:(-exact[i],-freq[i],i))[:8]
            result={}
            for rule in ("counts","unaligned","aligned"):
                packet,work=state.packet(aid,pool,freq,rule)
                assert packet==[(i,exact[i]) for i in expected]
                result[rule]=work
            assert result["aligned"]["pairs"]<=result["unaligned"]["pairs"]<=result["counts"]["pairs"]
            historic=state.all.get(aid,())
            result.update(t=t,sha=rev,anchor=aid,pool=len(pool),anchor_events=len(historic),
                          full_positions=sum(len(state.members[j]) for j in historic),rank=expected,
                          hits=sum(ids.get(p,-9) in expected for p in paths if p!=a),denom=len(paths)-1)
            results.append(result)
        encoded=[ids.setdefault(p,len(ids)) for p in paths]
        events.append(encoded)
        if t>=32:freq.subtract(events[t-32])
        freq.update(encoded)
        state.observe(encoded)
    return results,inventory(state)

def summarize(rows):
    return dict(n=len(rows),recall=fmean(r["hits"]/r["denom"] for r in rows),
                full_positions=sum(r["full_positions"] for r in rows),
                methods={m:dict(pairs=sum(r[m]["pairs"] for r in rows),prefix=sum(r[m]["prefix"] for r in rows),
                         resolved=sum(not r[m]["pairs"] for r in rows)) for m in ("counts","unaligned","aligned")})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    data=panels()
    totals={}
    for budget in (8,25):
        for name,repos in data.items():
            groups={};storage={}
            for repo,rows in repos.items():
                groups[repo],storage[repo]=replay(rows,name,budget)
            global_rows=[r for g in groups.values() for r in g]
            k=name+str(budget)
            totals[k]=dict(pooled=summarize(global_rows),per_project={p:summarize(g) for p,g in groups.items() if g},
                           storage=storage)
            dest=HERE/(k+"-cases.json.gz")
            if args.verify:assert load(dest)==groups
            else:save(dest,groups)
            print(k,totals[k]["pooled"],flush=True)
    if args.verify:assert load(HERE/"results.json")==totals
    else:save(HERE/"results.json",totals)
if __name__=="__main__":main()
