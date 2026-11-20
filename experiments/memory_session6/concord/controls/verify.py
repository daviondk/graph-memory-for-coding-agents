"""Standalone offline verification of the compact case table, all pair directions and token totals."""
import collections,math,re,string,sys
from util import *
def scores(a,b):
    def norm(x):
        x=x.lower().translate(str.maketrans('','',string.punctuation))
        return re.sub(r'\b(a|an|the)\b',' ',x).split()
    a,b=norm(a or ''),norm(b);hit=sum((collections.Counter(a)&collections.Counter(b)).values())
    return int(a==b),2*hit/(len(a)+len(b)) if a or b else 1.
def verify(suffix=''):
    rs=read(ROOT/('cases'+suffix+'.json.gz'));hy=read(ROOT/('results'+suffix+'.json'));ix=read(ROOT/('native_index'+suffix+'.json.gz'))
    arms=sorted(hy['arms']); ids=sorted({r['id'] for r in rs});assert len(ids)==40 and len(rs)==len(arms)*40
    keyed={(r['arm'],r['id']):r for r in rs};tc=collections.Counter()
    for r in rs:
        em,f1=scores(r['answer'],r['gold']);assert em==r['em'] and abs(f1-r['f1'])<1e-12
        for kind in ('prompt','completion'):
            assert sum((ix[x] or {}).get(kind) or 0 for x in r['receipt_refs'])==r[kind]
        assert all(ref.startswith(k+'@') for ref,k in zip(r['receipt_refs'],r['requests'],strict=True))
        tc[r['arm']]+=len(r['requests'])
        if r['arm']=='oracle':assert r['race'] in (0,None)
        if r['arm']!='git':assert 'diff' not in r['accepted'] or r['accepted']['diff']==0
    for a in arms:
        z=hy['arms'][a];xs=[keyed[a,i] for i in ids];assert z['em']==sum(x['em'] for x in xs) and abs(z['mean_f1']-sum(x['f1'] for x in xs)/40)<1e-12
        assert z['blinded_judge_correct']==sum(bool(x['judge']) for x in xs) and z['judge_missing']==sum(x['judge'] is None for x in xs)
        assert z['logical_requests']==tc[a]
        assert z['all_tool_attempts']==dict(sum((collections.Counter(x['tools']) for x in xs),collections.Counter()))
    for pair,res in hy['pairs'].items():
        a,b=pair.split(' minus ')
        observed=0;weights=collections.Counter();tied=0
        for sid in ids:
            for sign,arm in ((1,a),(-1,b)):
                row=keyed[arm,sid]
                if row['judge'] is None:weights[row['judge_key']]+=sign
                else:observed+=sign*int(row['judge'])
            tied+=int(keyed[a,sid]['judge'] is None and keyed[a,sid]['judge_key']==keyed[b,sid]['judge_key'])
        lo=(observed+sum(min(0,v) for v in weights.values()))/len(ids);hi=(observed+sum(max(0,v) for v in weights.values()))/len(ids)
        bounds=hy['judge_bounds'][pair]
        assert bounds['n']==len(ids) and bounds['identified_delta_interval']==[lo,hi] and bounds['shared_unknown_ties']==tied
        for e,data in res.items():
            if not isinstance(data,dict):continue
            delta=[]
            for i in ids:
                x,y=keyed[a,i],keyed[b,i]
                if x[e] is None or y[e] is None or e in ('prompt','completion') and (x['missing_usage'] or y['missing_usage']):continue
                delta.append(x[e]-y[e])
            assert data['paired_n']==len(delta)
            if not delta:continue
            w=sum(v>1e-12 for v in delta);l=sum(v< -1e-12 for v in delta)
            assert abs(data['delta']-sum(delta)/len(delta))<1e-9 and w==data['wins'] and l==data['losses']
            n=w+l;p=min(1.,2*sum(math.comb(n,j) for j in range(min(w,l)+1))/2**n) if n else 1.
            assert abs(p-data['exact_sign_p'])<1e-12
    expected=len(arms)*(len(arms)-1)//2;assert len(hy['pairs'])==expected
    return {'case_rows':len(rs),'pairs':expected,'complete_native_index_keys':len(ix),'answer_metrics_recomputed':True,'pair_discordances_and_sign_tests_independently_recomputed':True}
def main():
    x=verify();save(ROOT/'compact_verification.json',x);print(encode(x).decode())
    if (ROOT/'results_with_highlight.json').exists():
        y=verify('_with_highlight');save(ROOT/'compact_verification_with_highlight.json',y);print(encode(y).decode())
if __name__=='__main__':main()

