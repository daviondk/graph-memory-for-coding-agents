"""Stream the base and selected encoder tensors without loading them onto a GPU."""
from collections import defaultdict
import numpy as np
from safetensors import safe_open
from prepare import ROOT,RUN,pilot,load,put
def run():
    src=pilot.CACHE.parent/'e5-base-v2/model.safetensors';dst=RUN/'model/model.safetensors'
    assert pilot.sha(dst)==load(ROOT/'trained-checkpoint.json')['files']['model.safetensors']
    sums=defaultdict(float);details=[]
    with safe_open(src,framework='numpy') as a,safe_open(dst,framework='numpy') as b:
        ak=set(a.keys());bk=set(b.keys());assert ak-bk=={'embeddings.position_ids'} and not bk-ak
        assert np.array_equal(a.get_tensor('embeddings.position_ids'),np.arange(512,dtype=np.int64)[None,:])
        for k in sorted(bk):
            x=a.get_tensor(k);y=b.get_tensor(k);assert x.shape==y.shape
            d=y.astype('float64')-x
            norm=float(np.square(d).sum());base=float(np.square(x.astype('float64')).sum());cnt=int(np.count_nonzero(d))
            details.append(dict(key=k,parameters=x.size,changed_values=cnt,l2_change=norm**.5,relative_l2=(norm/base)**.5 if base else None,max_abs=float(np.abs(d).max())))
            sums['total_values']+=x.size;sums['changed_values']+=cnt;sums['delta_sq']+=norm;sums['base_sq']+=base
    put(ROOT/'weight-audit.json',dict(base_sha256=pilot.sha(src),checkpoint_sha256=pilot.sha(dst),parameters=int(sums['total_values']),
        excluded_buffer='embeddings.position_ids (nonpersistent int64 ramp 0..511)',changed_values=int(sums['changed_values']),total_tensors=len(details),changed_tensors=sum(d['changed_values']>0 for d in details),relative_l2=(sums['delta_sq']/sums['base_sq'])**.5,tensors=details))
if __name__=='__main__':run()
