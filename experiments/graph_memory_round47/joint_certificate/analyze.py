"""Score preservation of the whole ranked packet. Confidence intervals resample trajectories."""
from collections import Counter,defaultdict
import argparse
import numpy as np
from build import D,load,save
from geometry import probes,policies
METHODS=('box','hull_clipped','hull_full','recession')
def add(total,same,flags):
    total['n']+=1;total['same']+=int(same)
    for m,f in zip(METHODS,flags):
        total[m+'_tp']+=int(f and same);total[m+'_fp']+=int(f and not same)
def aggregate(by_q):
    rows=list(by_q.values());full=sum(rows,Counter());n=full['n'];same=full['same']
    out=dict(n=n,same=same,queries=len(rows),methods={})
    keys=['same']+[m+k for m in METHODS for k in ('_tp','_fp')]
    arr=np.array([[v[k]/v['n'] for k in keys] for v in rows])
    boot=np.random.default_rng(470532).multinomial(len(rows),[1/len(rows)]*len(rows),size=10000)/len(rows)
    def ci(col):
        point=float(col.mean());lo,hi=np.quantile(boot@col,[.025,.975]);return [point,float(lo),float(hi)]
    for i,m in enumerate(METHODS):
        tp=full[m+'_tp'];fp=full[m+'_fp'];out['methods'][m]=dict(tp=tp,fp=fp,precision=tp/(tp+fp) if tp+fp else None,recall=tp/same if same else None,
             correct_reuse=ci(arr[:,1+2*i]),unsafe_reuse=ci(arr[:,2+2*i]))
    out['full_minus_clipped']=ci(arr[:,5]-arr[:,3]);out['full_minus_recession']=ci(arr[:,5]-arr[:,7]);out['missed_full']=ci(arr[:,0]-arr[:,5])
    return out
def analyze():
    sample=load('sample.json.gz');outcomes=load('joint-outcomes.json.gz')
    groups=defaultdict(lambda:defaultdict(Counter));pop=Counter();witness={};ranks=Counter()
    for q,s in sample.items():
        available=s['available'];pop['available']+=available;pop['overlap_optional']+=s['all_optional_overlap'];pop['disjoint_active']+=s['all_disjoint_active']
        all_src=s['source'];cap=s['cap']
        eligible={i for i,c,u in s['tail'] if c<=cap}
        dups=Counter(i for ids in all_src.values() for i in ids)
        pop['multi_source_nodes']+=sum(v>1 for v in dups.values());pop['nodes_with_source']+=len(dups)
        for (a,b,mode),pred in zip(s['pairs'],outcomes[q],strict=True):
            active1=set(all_src[a])&eligible;active2=set(all_src[b])&eligible
            kind='overlap' if active1&active2 else 'disjoint' if active1 and active2 else 'inactive'
            grid,diagnostics=probes(s['limits'][a],s['limits'][b])
            pop[mode+'_pairs']+=1
            if mode=='primary':pop['primary_pairs_'+kind]+=1
            node_ids=lambda mask:[*s['head'],*[n for ch,(n,c,u) in zip(mask,s['tail']) if ch=='1']]
            for i,((dx,dy),phase) in enumerate([(point,'main') for point in grid]+[(point,'boundary') for point in diagnostics],1):
                mask=pred['table'][pred['idx'][i]]
                same=mask==s['old'];flags=policies(dx,dy,s['limits'][a],s['limits'][b])
                assert not (flags[1] or flags[2] or flags[3]) or same
                assert not flags[1] or flags[2]
                assert not flags[3] or flags[2]
                label=mode+'_'+phase
                add(groups[label][q],same,flags)
                if mode=='primary' and phase=='main':
                    add(groups['primary_'+kind][q],same,flags)
                    add(groups['primary_same_sign' if dx*dy>0 else 'primary_opposite_sign'][q],same,flags)
                if flags[0] and not same and label not in witness:
                    witness[label]=dict(query=q,mode=mode,kind=kind,source=[a,b],bounds=[s['limits'][a],s['limits'][b]],shift=[dx,dy],old=node_ids(s['old']),new=node_ids(mask))
                ranks[(label,kind,len(pred['table']))]+=1
    result={k:aggregate(x) for k,x in groups.items()}
    return dict(population=dict(pop),panels=result,first_unsafe=witness)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();out=analyze()
    if args.write:save('results.json',out)
    assert load('results.json')==out
    print('Population',out['population'])
    for key,v in out['panels'].items():
        print(key,v['n'],v['same'],{m:(a['tp'],a['fp']) for m,a in v['methods'].items()},v['full_minus_clipped'])

