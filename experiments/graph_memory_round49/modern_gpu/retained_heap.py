"""Budget reconstruction from the actual keys/ordering and exact resident array shapes."""
import sys
import numpy as np
from runner import D,LONG,P,BatchUpdate,put
sys.path.insert(0,str(LONG))
from heap_audit import deep


def main():
    raw=P.util.read(D/'receipts.json.gz')
    counts={}
    for repo,r in raw.items():
        counts[repo]={}
        for m,trace in r.items():
            pol=P.Cache('proposed',31,P.DigestKeys()) if m=='proposed' else BatchUpdate(m)
            resident={};sizes=[]
            for z in trace:
                keys=[bytes.fromhex(x) for x in z['doc_keys']]
                docs=dict(zip(keys,z['doc_tokens']));pending=resident.copy()
                for k in docs:
                    if k not in pending: pending[k]=np.zeros(4096,np.float32)
                if m=='proposed':
                    pol.operate(docs);wanted=pol.entries()
                else:
                    pol.update(docs);wanted=pol.res
                resident.clear()
                resident.update((k,pending[k].copy()) for k in wanted)
                assert sorted(k.hex() for k in wanted)==z['resident_out']
                seen=set();sizes.append(deep(pol,seen)+deep(resident,seen))
            counts[repo][m]=sizes
    peak={m:max(max(s[m]) for s in counts.values()) for m in ('s3','sieve','proposed')}
    put('heap.json',dict(sizes=counts,max_bytes=peak,limit=524288,scope='Recursively deduplicated resident Python objects after commit; excludes transient request objects and allocator slack'))
    print('Peak reconstructed resident Python bytes',peak)


if __name__=='__main__': main()

