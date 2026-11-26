"""Attach observed path and receipt after freezing, then compare all feasible withdrawals."""
from collections import Counter
import hashlib
import numpy as np
from project import D,W,R37,R38,read,save,sha
B=2048;T=1024

def select(rows):
    used=0;k=0
    for _,_,cost,_ in rows:
        if used+cost>T:break
        used+=cost;k+=1
    head=tuple(x[0] for x in rows[:k]);cap=B-used
    allowed=[x for x in rows[k:] if x[2]<=cap];best=np.zeros(cap+1,dtype=np.int64);take=[]
    for _,_,cost,utility in allowed:
        left=best[:cap+1-cost]+utility;update=left>best[cost:];np.maximum(best[cost:],left,out=best[cost:]);take.append((cost,update))
    suffix=[]
    for j in range(len(allowed)-1,-1,-1):
        cost,flags=take[j]
        if cap>=cost and flags[cap-cost]:suffix.append(allowed[j][0]);cap-=cost
    return head+tuple(reversed(suffix)),head,rows[k][0] if k<len(rows) else None

def main():
    frozen=read(D/'plan-seal.json');assert sha(D/'plans.json.gz')==frozen['plans'] and sha(D/'PROTOCOL_RU.md')==frozen['protocol']
    plans=read(D/'plans.json.gz');schedule=read(R38/'schedule.json.gz');cpath=R37/'code_visibility/events.json.gz';bpath=R37/'edit_demand/native_boundaries.json.gz'
    for path in (cpath,bpath):assert sha(path)==read(path.parent/'manifest.json')['files'][path.name]
    corpus,receipt=read(cpath),read(bpath);observed=[];operations=Counter();controls=0;tests=0
    for rid,v in schedule.items():
        lookup={e[0]:e for e in corpus[rid]['events']};accepted={a:(ty,path) for a,_,ty,path in receipt[rid].get('successful_writes',[])}
        for e in v['events']:
            at,kind,*args=e
            if kind not in ('snapshot+invalidate','invalidate'):continue
            event=lookup[at];path=args[0];assert hashlib.sha256(event[2].encode()).hexdigest()==path
            operations[event[1]]+=1
            if event[1]!='write_start':continue
            if at in accepted:
                op,verified=accepted[at];assert verified==path
                status='confirmed_replacement' if op=='str_replace' else 'confirmed_other'
            else:status='unconfirmed_attempt'
            if kind=='snapshot+invalidate':assert status=='confirmed_replacement'
            entries=plans[rid][str(at)];rows=[(i,r[0],r[3],r[4]) for i,r in enumerate(entries)];candidates=sorted({r[1] for r in rows});base,head,barrier=select(rows);selected={rows[i][1] for i in base};guard=selected|({rows[barrier][1]} if barrier is not None else set())
            by_path={};tests+=1
            for deleted in candidates:
                after,new_head,_=select([r for r in rows if r[1]!=deleted]);changed=after!=base
                exact=deleted not in selected and set(new_head)<=set(base);safe=deleted not in guard
                assert exact==(not changed) and (not safe or after==base)
                by_path[deleted]=(int(changed),int(safe));controls+=1;tests+=1
            actual=by_path.get(path,(0,1));n=len(candidates);picked=None
            if n:
                label=f'r40-natural-path-v1|{rid}|{at}';picked=candidates[int(hashlib.sha256(label.encode()).hexdigest(),16)%n]
            sampled=by_path.get(picked,(0,1));mean=tuple(sum(v[i] for v in by_path.values())/n for i in range(2)) if n else (0.,1.)
            observed.append(dict(rid=rid,event=at,group=v['group'],issue=v['issue'],repo=v['repo'],receipt=status,actual=path,draw=picked,paths=n,present=path in by_path,units=len(rows),selected=len(base),bytes=sum(rows[i][2] for i in base),barrier=barrier,actual_changed=actual[0],actual_safe=actual[1],random_changed=mean[0],random_safe=mean[1],draw_changed=sampled[0],draw_safe=sampled[1],by_path=by_path))
    save(D/'observations.json.gz',observed);save(D/'score-seal.json',dict(source_types=sha(cpath),source_receipts=sha(bpath),plan_seal=sha(D/'plan-seal.json'),code=sha(D/'score.py'),outcomes=sha(D/'observations.json.gz'),operation_counts=dict(operations),attempts=len(observed),all_possible_path_withdrawals=controls,full_dp_calls=tests));print('attempts',len(observed),'withdrawals',controls,'event classes',dict(operations))
if __name__=='__main__':main()
