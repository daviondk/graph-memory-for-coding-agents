import csv
import math
import random
import statistics
from collections import Counter
from functools import lru_cache
from common import *
from policies import allocation

@lru_cache(None)
def cost(key):
    d=read('calls/'+key+'.json.gz');u=d['response']['usage']
    return (u['prompt_tokens'],u['completion_tokens'],d['seconds'])
def contrast(rows,a,b,filter_ids=None):
    sel=[r for r in rows if filter_ids is None or r['id'] in filter_ids]
    if not sel:return None
    pairs=[(int(r['passes'][a])-int(r['passes'][b]),r['changed']) for r in sel]
    n=len(pairs);w=sum(x==1 for x,_ in pairs);l=sum(x==-1 for x,_ in pairs);k=w+l
    p=min(1,2*sum(math.comb(k,i) for i in range(min(w,l)+1))/(2**k)) if k else 1.
    strata=[[v for v,z in pairs if z==g] for g in (False,True)];rng=random.Random(18062026)
    samples=sorted(100*sum(sum(rng.choices(x,k=len(x))) for x in strata if x)/n for j in range(10000))
    return dict(n=n,wins=w,losses=l,ties=n-k,delta_pp=(w-l)*100/n,lower_pp=samples[249],upper_pp=samples[9749],p=p,
                won_ids=[r['id'] for r in sel if r['passes'][a] and not r['passes'][b]],
                lost_ids=[r['id'] for r in sel if not r['passes'][a] and r['passes'][b]])
def summarize(rows,prefixes,branches,ids,alloc):
    index={r['id']:r for r in rows};counts={}
    for policy,mapping in alloc.items():
        writer=policy.endswith('_note')
        target=[index[i] for i in ids if i in index]
        costs=[]; delivered=[]; readbytes=0;oldbytes=0; oldcalls=0; metabytes=0
        for r in target:
            i=r['id'];b=mapping[i];branch=branches[i,b];c=cost(branch['call']);p=prefixes[i]
            if writer:
                wc=cost(p['call']);c=tuple(a+y for a,y in zip(c,wc));oldcalls+=1
            if policy!='always_current':oldbytes+=p['old_bytes']
            if policy in ('version_note','version_raw','hybrid_note'):
                metabytes+=(ROOT/path(i,'current.txt')).stat().st_size
            if b=='current':readbytes+=branch['delivered_bytes']
            delivered.append(branch['delivered_bytes']);costs.append(c)
        counts[policy]=dict(n=len(target),solve=sum(r['passes'][policy] for r in target),rereads=sum(mapping[r['id']]=='current' for r in target),changed_solves=sum(r['passes'][policy] for r in target if r['changed']),unchanged_solves=sum(r['passes'][policy] for r in target if not r['changed']),prompt_tokens=sum(x[0] for x in costs),completion_tokens=sum(x[1] for x in costs),seconds=round(sum(x[2] for x in costs),3),reread_bytes=readbytes,old_read_bytes=oldbytes,sha_provider_current_bytes=metabytes,reader_payload_bytes=sum(delivered),writer_calls=oldcalls)
    return counts
def blind_expectation(rows):
    vals=[int(r['branch_pass']['current'])-int(r['branch_pass']['note']) for r in rows]
    return sum(r['branch_pass']['note'] for r in rows)+sum(vals)/2
def build(scores,cohort):
    allitems=[r for r in read('roster.json')['items'] if r['cohort']==cohort]
    ids=[r['id'] for r in allitems];pref={i:read(path(i,'prefix.json')) for i in ids}
    alloc=allocation(allitems,pref); assert alloc=={a:{int(i):b for i,b in vs.items()} for a,vs in read('allocations.json')[cohort].items()}
    branches={(i,b):read(path(i,b+'.json')) for i in ids for b in ('note','raw','current')}
    rows=[]; ledger=[]
    for it in allitems:
        i=it['id'];s=scores[str(i)]
        if not s.get('covered',True):continue
        passed={b:s[b]['status']=='pass' for b in ('note','raw','current')}
        row=dict(id=i,changed=it['changed'],branch_pass=passed,passes={m:passed[a[i]] for m,a in alloc.items()})
        rows.append(row)
        for m,a in alloc.items():
            b=a[i];x=branches[i,b];co=cost(x['call']);wc=cost(pref[i]['call']) if m.endswith('_note') else (0,0,0)
            ledger.append(dict(cohort=cohort,id=i,changed=it['changed'],interface=it['interface'],policy=m,branch=b,
                 reread=b=='current',status=s[b]['status'],old_sha=it['old_sha'],current_sha=it['current_sha'],ambiguity=pref[i]['ambiguity'],writer_call=pref[i]['call'] if m.endswith('_note') else '',reader_call=x['call'],candidate_sha=x['code_sha'],prompt_tokens=co[0]+wc[0],completion_tokens=co[1]+wc[1],seconds=round(co[2]+wc[2],3),reader_payload_bytes=x['delivered_bytes']))
    allids={r['id'] for r in rows};ref='plus_reference' if any('plus_reference' in scores[str(i)] for i in ids) else 'reference'
    good={i for i in allids if scores[str(i)][ref]['status']=='pass' and scores[str(i)]['stub']['status']!='pass'}
    no_timeout={i for i in allids if all(scores[str(i)][b]['status']!='timeout' for b in ('note','raw','current','reference','stub',ref))}
    baseline_budget={m:sum(x=='current' for x in a.values()) for m,a in alloc.items()}
    for a in ('version_note','blind_note','uncertainty_note','hybrid_note','version_raw','blind_raw'):assert baseline_budget[a]==len(allitems)//2
    allrows=summarize(rows,pref,branches,allids,alloc)
    def stats(ids_):
        return {b:dict(Counter(scores[str(i)][b]['status'] for i in ids_)) for b in ('reference',ref,'stub','note','raw','current')}
    expected=blind_expectation(rows)
    comparisons={a+'-vs-'+b:contrast(rows,a,b) for a,b in [('version_note','blind_note'),('version_note','uncertainty_note'),('version_note','hybrid_note'),('version_raw','blind_raw'),('version_note','version_raw'),('version_note','always_current'),('version_note','never_note'),('always_current','never_note'),('always_current','never_raw')]}
    result=dict(n=len(allrows) and len(rows),coverage_ids=sorted(allids),missing_ids=sorted(set(ids)-allids),valid_ids=sorted(good),no_timeout_ids=sorted(no_timeout),statuses=stats(allids),cohort_budgets=baseline_budget,policy=allrows,valid=summarize(rows,pref,branches,good,alloc),contrast=comparisons,
                primary_valid=contrast(rows,'version_note','blind_note',good),primary_no_timeout=contrast(rows,'version_note','blind_note',no_timeout),expected_blind_solves=expected,
                complete_note_pairs=sum(pref[i]['valid'] for i in ids),unchanged_raw_equals_current=sum((ROOT/path(i,'current.txt')).read_bytes().decode()==pref[i]['raw'] for i in ids), note_tokens=[pref[i]['note_tokens'] for i in ids],raw_tokens=[pref[i]['raw_tokens'] for i in ids],
                by_version={str(v):{'n':sum(r['changed']==v for r in rows),'read_vs_note':contrast([r for r in rows if r['changed']==v],'always_current','never_note'),'read_vs_raw':contrast([r for r in rows if r['changed']==v],'always_current','never_raw')} for v in (True,False)})
    return result,ledger
def main():
    check(read('prediction_lock.json')['hashes'])
    res={};ledger=[]
    for outcome,filename in [('author','scores.json'),('enhanced','plus_scores.json')]:
        if not (ROOT/filename).exists():continue
        scores=read(filename);res[outcome]={}
        for c in ('primary','replication'):
            result,rows=build(scores,c);res[outcome][c]=result
            ledger.extend(dict(endpoint=outcome,**r) for r in rows)
    save('results.json',res)
    with (ROOT/'item_results.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(ledger[0]));writer.writeheader();writer.writerows(ledger)
    calls=list((ROOT/'calls').glob('*.json.gz')); us=[cost(p.name.split('.')[0]) for p in calls]
    save('native_costs.json',dict(unique_calls=len(us),prompt_tokens=sum(u[0] for u in us),completion_tokens=sum(u[1] for u in us),seconds=round(sum(u[2] for u in us),3)))
    print('policy summaries and',len(ledger),'item-policy rows')
if __name__=='__main__':main()

