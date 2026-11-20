"""Post-protocol diagnostic: bound an address-only repair on the actual sealed R5 text."""
import base64
import collections
import gzip
import json
from replay import HERE, old, jobs, inputs, save, check, locks


def main():
    check('evaluation_lock.json')
    outcomes={(r['panel'],r['id'],r['cut']):r for r in old.rr(HERE/'block_outcomes.jsonl.gz')}
    sums=collections.defaultdict(collections.Counter)
    with gzip.open(HERE/'headroom_records.jsonl.gz','wt',encoding='utf8') as out:
        for panel,k in jobs():
            src,_=inputs(panel,k);states=iter(old.rr(HERE/f'states_{panel}_{k}.gz'))
            for task in old.rr(src):
                events=task['events'];iid=task['instance']
                for step in range(1,len(events)+1):
                    i,j,blobs,_=next(states)
                    assert (i,j)==(iid,step)
                    r=outcomes.get((panel,iid,step))
                    if not r:continue
                    values=old.prior.materialize(old.decode(base64.b64decode(blobs['r5'])[1:]))[1]['rebase'].get(r['path'],{})
                    args,obs=old.anchor.future_check(events,step)
                    lo,target=old.anchor.invert(args,obs)
                    starts=[n for n,(s,_) in values.items() if s==target[0] and all(values.get(n+x,[None])[0]==v for x,v in enumerate(target))]
                    texts=collections.Counter(v[0] for v in values.values())
                    enough=not(collections.Counter(target)-texts)
                    shifted=bool(starts)
                    assert (lo in starts)==bool(r['out']['r5']['full']) and not(shifted and not enough)
                    bucket='already_full' if lo in starts else 'common_translation' if shifted else 'independent_permutation' if enough else 'insufficient_retained_text'
                    sums[panel][bucket]+=1
                    old.write(out,[panel,iid,step,bucket,[n-lo for n in starts],len(values),r['last_shell']])
            assert next(states,None) is None
    save('headroom.json',sums)
    print(json.dumps(sums))


if __name__=='__main__':main()
