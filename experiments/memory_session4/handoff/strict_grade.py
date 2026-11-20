import collections
from common import *
from grade import stats,delta

def main():
    check('strict_grade_lock.json')
    lock=read('strict/reader_lock.json');assert all(sha((ROOT/'strict'/k).read_bytes())==v for k,v in lock.items())
    ds=read('strict/choices.json');assert len(ds)==192
    main=read('score_vectors.json.gz')['reader']['clean'];ids=main['ids'];labels=read('labels.json.gz');mp={'claude':'claude','codex':'gemini'}
    by={(r['issue'],r['reverse']):r for r in ds};values=[];picked=[];invalid=0;unstable=0
    for i in ids:
        raw=[by[i,r]['choice'] for r in (False,True)];p=[mp[c or pick(i)] for c in raw]
        picked+=p;invalid+=raw.count(None);unstable+=p[0]!=p[1]
        values.append(sum(labels[m+'|'+i]['resolved'] for m in p)/2)
    report={'n':len(ids),'metrics':stats(values),'invalid':invalid,'order_disagreement':unstable,'picked_source':dict(collections.Counter(picked)),
            'nominal_total_tokens':sum(r['usage']['total_tokens'] for r in ds),
            'contrasts':{key:delta(values,main['values'][key],main['groups']) for key in ('empty','latest','witness','heldout_repository_prior')}}
    write('strict/results.json',report);write('strict/score_vectors.json',{'ids':ids,'values':values})
    print(canon(report))
if __name__=='__main__':main()
