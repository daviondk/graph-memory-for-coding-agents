"""Post-hoc distribution stress tests on sealed states. No solver or gold outcomes."""
import base64,hashlib
from collections import Counter,defaultdict
import statistics
from common import ROOT,load,put,verify
from reader import read
from ef_reader import decode

def main():
    verify(load(ROOT/'state_seal.json')['local']);verify(load(ROOT/'ef_seal.json'))
    states=sorted((ROOT/'states').rglob('*.gz'))
    futures={}
    for p in (ROOT/'future').rglob('*.gz'):
        d=load(p);futures[d['issue'],d['direction']]=d['changed']
    caserows=[];stats=defaultdict(Counter);rstats=defaultdict(Counter)
    for p in states:
        d=load(p);issue=d['issue'];direction=d['direction'];n=d['n']
        old=load(ROOT/'old'/d['panel']/p.name)['sets']
        truth=defaultdict(int)
        for i,words in enumerate(old):
            for w in words:truth[w]|=1<<i
        absent=['__R10_absent__/'+hashlib.sha256(f'{issue}/{direction}/{i}'.encode()).hexdigest() for i in range(256)]
        assert len(set(absent))==256 and not(set(absent)&truth.keys())
        qs=[(t,q) for (t,s),q in sorted(futures.items()) if t!=issue and s==direction]
        def expected(q):
            total=0
            for w in q:total|=truth.get(w,0)
            return total
        others=[(t,q,expected(q),sum(w in truth for w in q)) for t,q in qs]
        assert len(others)==17
        e=load(ROOT/'ef_states'/d['panel']/p.name)
        old_sample=sorted(truth,key=lambda w:hashlib.sha256(w.encode()).digest())[:32]
        for row in d['states']+e['states']:
            s=row['salt'];b=row['b'];arm=row['arm']
            if s not in (0,7,19):continue
            raw=base64.b64decode(row['data']);call=decode(raw) if arm=='elias_fano' else lambda q:read(raw,q)
            neg=sum(call([w]).bit_count() for w in absent)
            cross=[];c=Counter()
            for t,q,mask,on_graph in others:
                out=call(q);assert out&mask==mask
                extras=(out^mask).bit_count()
                cross.append([t,len(q),on_graph,mask,out])
                c.update(extra=extras,expected=mask.bit_count(),queries=1,keys=len(q),in_graph=on_graph,total_tests=n)
            sample=sorted(truth) if s==0 and arm=='xor_map' else old_sample
            extra_known=0
            for w in sample:
                o=call([w]);assert o&truth[w]==truth[w]
                extra_known+=(o^truth[w]).bit_count()
            caserows.append(dict(panel=d['panel'],issue=issue,direction=direction,b=b,salt=s,arm=arm,n=n,absent_fp_bits=neg,negative_singletons=len(absent),cross=cross,known_verified=len(sample),known_extra_bits=extra_known))
            stats[b,arm,s].update(c)
            stats[b,arm,s].update(negative_tests=n*len(absent),negative_bits=neg)
            if s==0:rstats[b,arm].update(known=len(sample),extra_known=extra_known)
    summary={}
    for (b,arm,s),x in stats.items():
        reports=summary.setdefault(b,{}).setdefault(arm,{})
        reports['salt'+str(s)]=dict(**x,negative_rate=x['negative_bits']/x['negative_tests'],cross_rate=x['extra']/x['total_tests'])
    for b,cell in summary.items():
        for arm,box in cell.items():
            v=list(box.values())
            box['avg_negative_rate']=statistics.mean(x['negative_rate'] for x in v)
            box['avg_cross_extra']=statistics.mean(x['extra'] for x in v)
            box['avg_cross_rate']=statistics.mean(x['cross_rate'] for x in v)
            box['verified_salt0']=dict(rstats[b,arm])
    put(ROOT/'challenge_rows.json.gz',caserows);put(ROOT/'challenge_results.json',summary)
    for b,cell in summary.items():
        for arm,v in cell.items():print(b,arm,round(v['avg_negative_rate'],5),round(v['avg_cross_extra'],2),v['verified_salt0'])
if __name__=='__main__':main()