from common import *
from grade import cluster_interval,delta,stats
import collections

def main():
    check('control_grade_lock.json')
    lock=read('shuffle/reader_lock.json');assert all(sha((ROOT/'shuffle'/k).read_bytes())==v for k,v in lock.items())
    ds=read('shuffle/choices.json');assert len(ds)==192
    main=read('score_vectors.json.gz')['reader']['clean'];ids=main['ids'];labels=read('labels.json.gz');mapping={'claude':'claude','codex':'gemini'}
    by={(r['issue'],r['reverse']):r for r in ds};values=[];picked=[];invalid=0;unstable=0
    for i in ids:
        raw=[by[i,r]['choice'] for r in (False,True)];p=[mapping[c or pick(i)] for c in raw]
        picked+=p;invalid+=raw.count(None);unstable+=p[0]!=p[1]
        values.append(sum(labels[m+'|'+i]['resolved'] for m in p)/2)
    report={'n':len(ids),'metrics':stats(values),'invalid':invalid,'order_disagreement':unstable,'picked_source':dict(collections.Counter(picked)),
            'nominal_total_tokens':sum(r['usage']['total_tokens'] for r in ds),
            'correct_minus_permuted':delta(main['values']['witness'],values,main['groups']),
            'permuted_minus_empty':delta(values,main['values']['empty'],main['groups']),
            'same_issue_patch_all_arms':True}
    write('shuffle/results.json',report);write('shuffle/score_vectors.json',{'ids':ids,'values':values})
    print(canon(report))
if __name__=='__main__':main()
