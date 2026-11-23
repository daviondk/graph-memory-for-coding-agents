"""Verify parent-disjointness, identical prompts, exact population probabilities and costs."""
import collections
import itertools
import json
import math

from gate import ROOT,R17,read,sha,compact,prompt,lexical
def main():
    for name in ('design.lock.json','response.lock.json','read.lock.json'):
        for n,h in read(ROOT/name).items():assert sha((ROOT/n).read_bytes())==h
    old={r['id'] for r in read(R17/'menus.json.gz')}
    routes={r['id']:r for r in read(ROOT/'route.json')}
    assert not old.intersection(routes) and len(old|set(routes))==54
    res=read(ROOT/'results.json')
    calls={r['sha']:r for r in (json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines())}
    prompts=read(ROOT/'prompts.json.gz');assert set(prompts)==set(calls)
    assert all(sha(v.encode())==k for k,v in prompts.items()) and all(sha(v['raw'].encode())==v['response_sha'] for v in calls.values())
    used=[r for r in read(ROOT/'annotated.json.gz') if r['available']]
    # Independent multivariate hypergeometric calculation, using only the number of gain, loss and neutral cases.
    delta=collections.Counter(int(r['qwen']['hits']>0)-int(r['static']['hits']>0) for r in used)
    n=res['quota'];base=res['policies']['static']['hits'];hist=collections.Counter()
    for wins in range(delta[1]+1):
        for losses in range(delta[-1]+1):
            other=n-wins-losses
            if 0<=other<=delta[0]:
                hist[base+wins-losses]+=math.comb(delta[1],wins)*math.comb(delta[-1],losses)*math.comb(delta[0],other)
    assert {str(k):n for k,n in hist.items()}==res['policies']['expected_uniform']['histogram']
    for kind in ('gap','hash'):
        chosen=[calls[r['sha']] for r in routes.values() if r['route_'+kind]]
        got=res['policies'][kind];assert len(chosen)==got['calls']
        assert all(sum(v['usage'][k] for v in chosen)==got[k] for k in ('prompt_tokens','completion_tokens'))
    print('30 disjoint tasks;',len(calls),'native payloads/responses;',sum(hist.values()),'uniform assignments; recorded costs agree')
if __name__=='__main__':main()
