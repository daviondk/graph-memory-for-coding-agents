"""Quantify the CPU fallback and keep a paired GPU-only strict sensitivity."""
import collections
from common import *
from grade import stats,delta
def main():
    rt=ROOT.parent/'runtime'
    service=json.loads((rt/'service-resumed.json').read_bytes())
    events=[json.loads(x) for x in (rt/'requests.jsonl').read_text().splitlines()]
    by={e['id']:e for e in events}
    rows=read('strict/choices.json')
    by_issue=collections.defaultdict(list);types=collections.Counter()
    for r in rows:
        typ='CPU_after_CUDA_fault' if by[r['response_id']]['epoch']>=service['utc_epoch'] else 'GPU'
        types[typ]+=1;by_issue[r['issue']].append(typ)
    ids=sorted(i for i,backends in by_issue.items() if backends==['GPU','GPU'])
    main=read('score_vectors.json.gz')['reader']['clean'];strict=read('strict/score_vectors.json')
    sv=dict(zip(strict['ids'],strict['values']));positions={i:j for j,i in enumerate(main['ids'])}
    values=[sv[i] for i in ids];groups=[main['groups'][positions[i]] for i in ids]
    refs={k:[main['values'][k][positions[i]] for i in ids] for k in ('empty','latest','witness','heldout_repository_prior')}
    result={'assignments_by_backend':dict(types),'native_calls_by_backend':dict(collections.Counter('CPU_after_CUDA_fault' if e['epoch']>=service['utc_epoch'] else 'GPU' for e in events)),
            'included_gpu_only_issues':ids,'n_complete_gpu_pairs':len(ids),'metrics':{'strict':stats(values),**{k:stats(v) for k,v in refs.items()}},
            'contrasts':{k:delta(values,v,groups) for k,v in refs.items()},
            'backend_boundary':service['utc_epoch'],'primary_clean_all_gpu':all(by[r['response_id']]['epoch']<service['utc_epoch'] for r in read('clean/choices.json'))}
    write('strict/backend_sensitivity.json',result)
    print(canon(result))
if __name__=='__main__':main()
