"""Exact output parity against the sealed decoder plus an equivalent cold-lookup timing."""
import base64,statistics,hashlib
from collections import defaultdict
from common import ROOT,load,put,verify
from ef_reader import decode
from ef_direct import lookup
from timing import measure
def main():
    verify(load(ROOT/'ef_seal.json'));chosen=load(ROOT/'timing_results.json')['issues']
    rows=[];calls=0
    for p in sorted((ROOT/'ef_states').rglob('*.gz')):
        d=load(p);old=load(ROOT/'old'/p.parent.name/p.name);q=load(ROOT/'future'/p.parent.name/p.name)['changed']
        keys=set().union(*(set(z) for z in old['sets']));samples=sorted(keys,key=lambda w:hashlib.sha256(w.encode()).digest())[:5]
        probes=[q]+[[a] for a in samples]+[['__R10_absent_direct__/'+str(i)] for i in range(5)]
        for r in d['states']:
            raw=base64.b64decode(r['data']);ref=decode(raw)
            for words in probes:
                assert ref(words)==lookup(raw,words)
                calls+=1
            if r['salt']==0 and d['issue'] in chosen:rows.append(dict(issue=d['issue'],direction=d['direction'],b=r['b'],timing=measure(lambda:lookup(raw,q))))
    put(ROOT/'ef_direct_results.json',dict(compared=calls,summary={b:statistics.median(r['timing']['cpu_ns'] for r in rows if r['b']==b)/1000 for b in [64,256]},rows=rows))
if __name__=='__main__':main()