"""Reconstruct persistent Python objects exactly; separate retained arrays from transient packet memory."""
import sys,json,hashlib,gzip
from run_gpu import D,Cache,GD,COUNT,DigestKeys,DigestInts,util,np
def deep(obj,seen):
    k=id(obj)
    if k in seen:return 0
    seen.add(k);v=sys.getsizeof(obj)
    if isinstance(obj,dict):v+=sum(deep(x,seen)+deep(y,seen) for x,y in obj.items())
    elif isinstance(obj,(list,tuple,set)):v+=sum(deep(x,seen) for x in obj)
    elif hasattr(obj,'__dict__'):v+=deep(obj.__dict__,seen)
    return v
def main():
    data=util.read(D/'raw-runs.json.gz');results={};types={}
    for rep,rr in data.items():
        for method in ('proposed','lru','gdsf'):
            pol=GD('batch',COUNT,DigestInts()) if method=='gdsf' else Cache('hot_lru' if method=='lru' else method,COUNT,DigestKeys());persistent={};measure=[]
            for z in rr[method]:
                keys=[bytes.fromhex(x) for x in z['doc_keys']];docs=dict(zip(keys,z['doc_tokens']));cache=persistent.copy()
                for k in docs:
                    if k not in cache:cache[k]=np.zeros(4096,np.float32)
                if method=='gdsf':pol.update(docs);wanted=list(pol.res)
                elif method=='proposed':pol.operate(docs);wanted=list(pol.entries())
                else:
                    seq=sorted(docs,key=lambda k:(docs[k],-int.from_bytes(k,'big')));pol.operate({k:docs[k] for k in seq});wanted=list(pol.entries())
                persistent.clear();persistent.update((k,cache[k].copy()) for k in wanted);assert sorted(k.hex() for k in persistent)==z['resident_out']
                seen=set();n=deep(persistent,seen)+deep(pol,seen);measure.append(n)
            results[rep+' / '+method]=measure;types.setdefault(method,[]).extend(measure)
    util.put('heap.json',dict(measurements=results,max={k:max(v) for k,v in types.items()},min={k:min(v) for k,v in types.items()},
        cap=524288,python=sys.version,scope='getsizeof recursive identity-deduplicated own resident arrays and policy objects after commit, replay with actual numeric layouts; excludes interpreter, allocator, RPC and transient request buffers'))
    print('Replayed actual heap-object maxima', {k:max(v) for k,v in types.items()})
if __name__=='__main__':main()

