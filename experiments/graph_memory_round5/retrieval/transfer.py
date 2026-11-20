from budget import *
from collections import defaultdict
def allocate(order,pr,budget):
    # Tie-breaking prefers lower depth; prevents uninformative ties from filling one request first.
    depth=[1]*len(order);heap=[(-pr[key][1],2,i) for i,key in enumerate(order) if len(pr[key])>=2];heapq.heapify(heap)
    for _ in range(budget-len(order)):
        _,l,i=heapq.heappop(heap);depth[i]=l;key=order[i]
        if l<len(pr[key]):heapq.heappush(heap,(-pr[key][l],l+1,i))
    return depth
def main():
    lock=load(D/'budget_model.json');weights=load(D/'rank_weights.json')
    jtrain={r[2] for r in inputs(R/'full.pred.jsonl.gz')};jtest={r[2] for r in inputs(R/'archive.pred.jsonl.gz')}
    outputs=[];by={}
    for lang in ('python','java'):
        if lang=='java':rows=list(inputs(R/'archive.pred.jsonl.gz'));skipped=set()
        else:
            allrows=[(p,j,repo,[arms['graph']]) for p,j,k,repo,s,h,e,arms in rr(R/'python.pred.jsonl.gz') if k==3];rows=[row for row in allrows if row[2] not in jtrain|jtest];skipped={r[2] for r in allrows if r[2] in jtrain|jtest}
        by[lang]=dict(n=len(rows),projects=len({z[2] for z in rows}),excluded=sorted(skipped));lookup={};ps=defaultdict(dict)
        for p,j,repo,o in rows:
            key=p,j;n=len(o[0]);r=positions([o[0]])[:,0];limit=min(8,n);pos=np.arange(1,n+1);lookup[key]=n,repo
            ps['uniform'][key]=np.full(limit,1/n);ps['harmonic'][key]=(1/pos/(1/pos).sum())[:limit]
            ps['count_model'][key]=monotone(soft(base(r)@lock['base']['weights'])[o[0]][:limit])
            if lang=='java':
                f=transform(o,p+'|'+str(j))
                for arm in ('linear','additive','adaptive'):
                    ps[arm][key]=monotone(soft(f[arm]@weights[arm]['weights'])[o[0]][:limit])
        ordered=sorted(lookup,key=lambda key:sha('budget5|'+key[0]+'|'+str(key[1])))
        for mode in ('mixed','level','exact_n'):
            groups=defaultdict(list)
            for key in ordered:
                g={'mixed':'all','level':key[0].rsplit('_',1)[-1],'exact_n':str(lookup[key][0])}[mode];groups[g].append(key)
            for g,group in groups.items():
                for off in range(0,len(group),32):
                    chunk=group[off:off+32];budget=sum(min(3,lookup[key][0]) for key in chunk)
                    methods={a:allocate(chunk,v,budget) for a,v in ps.items()}
                    for i,(p,j) in enumerate(chunk):
                        depth={'fixed':min(3,lookup[p,j][0]),**{a:l[i] for a,l in methods.items()}}
                        outputs.append(dict(language=lang,mode=mode,panel=p,idx=j,project=lookup[p,j][1],depth=depth,block=g+'-'+str(off)))
        print(lang,len(rows),flush=True)
    jsonrows('transfer_predictions.jsonl.gz',outputs)
    dump('transfer_lock.json',dict(utc=now(),rows=by,pred=filehash(D/'transfer_predictions.jsonl.gz'),model=filehash(D/'budget_model.json'),ranks=filehash(R/'python.pred.jsonl.gz'),protocol=filehash(D/'TRANSFER_PROTOCOL_RU.md'),amendment=filehash(D/'TRANSFER_AMENDMENT_RU.md'),file=filehash(D/'transfer.py')))
if __name__=='__main__':main()

