"""Independent dataset traversal and rank-based counts; do not call the evaluation metrics."""
import json,gzip,collections,hashlib,math,sys,re
from prepare import P,read,write,sha
def main():
    raw=read("upstream/locomo10.json");r=json.loads(gzip.decompress((P/"predictions.json.gz").read_bytes()))
    numbers=collections.defaultdict(lambda:collections.Counter());labels={};words=collections.defaultdict(set);group_ids={}
    for conv in raw:
        c=conv['sample_id'];tr={t['dia_id'] for s,L in conv['conversation'].items() if re.fullmatch(r'session_\d+',s) for t in L}
        for j,a in enumerate(conv['qa']):
            i=f"{c}:{j}";assert i in r;words[a['question'].casefold().strip()].add(c)
            for method,lists in r[i].items():
                assert set(lists[0])<=tr and len(set(lists[0]))==len(lists[0])==30
            if a['category']==5:continue
            gold=set(a['evidence']);sid=set('session_'+m[1] for x in gold if (m:=re.match('D([0-9]+)',x)))
            if gold and gold<=tr:
                labels[i]=a;group_ids.setdefault(c,[]).append(i)
            for key,good,valid,jj in [('turn',gold,bool(gold and gold<=tr),0),('session',sid,bool(sid),1)]:
                if not valid:continue
                for m,rr in r[i].items():
                    top=rr[jj][:5];out=numbers[key,m];out['n']+=1;out['all@5']+=all(x in top for x in good);out['any@5']+=any(x in top for x in good)
                    out['recall@5']+=sum(x in top for x in good)/len(good)
    results=read('retrieval_results.json')['results']
    for (k,m),v in numbers.items():
        assert v['n']==results[k]['n']
        for met in ('any@5','all@5','recall@5'):assert abs(v[met]/v['n']-results[k]['metrics'][m][met])<1e-12
    pool=read('reader_lock.json')['questions']
    for c,ids in group_ids.items():
        assert [x for x in pool if x.startswith(c+':')]==sorted(ids,key=lambda i:sha('r3-reader|'+i))[:35]
    script=(P/'rank.py').read_text();assert 'other=[t for key,t in train.items() if key!=k]' in script
    seen=collections.Counter(x['cat'] for x in read('gold.json').values())
    duplicate={k:v for k,v in words.items() if len(v)>1}
    audit=dict(checked_all5_cells=sum(v['n'] for v in numbers.values()),question_count=len(r),turn_eligible=len(labels),pilot_scope=len(pool),sessions_diagnostic_n=results['session']['n'],agreement=True,queries_repeated_across_conversations=len(duplicate),category_counts=dict(seen),roles_in_input=['text','caption','time','speaker','session','id'],n_conversations=len(raw),test_retriever_crossfit='leave one conversation out')
    if (P/'transfer_output.json').exists():
        lock=read('transfer_lock.json'); assert not set(pool)&set(lock['items']);assert set(pool)|set(lock['items'])==set(labels)
        assert sha((P/'transfer_output.json').read_bytes())==read('transfer_receipt.json')['sha256']
        audit.update(transfer_scope=len(lock['items']),transfer_disjoint=True)
    write("audit.json",audit)
if __name__=='__main__':main()