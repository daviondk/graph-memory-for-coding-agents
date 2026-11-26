"""Extract original binary64 utilities by calling R39 batch code, without access to gold."""
import os
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
from common import D,W,SEEDS,put,read,sha
import gzip,sys
import numpy as np
sys.path.insert(0,str(W/"graph_memory_round39/global_packet"))
import packet
model=read(W/"graph_memory_round39/global_packet/models.json")["models"]["graph"]
receipts={}
for seed in SEEDS:
    ref,mat=packet.projections("test",seed)
    values=np.logaddexp(0,packet.portable(model,mat[:,model["cols"]]))
    assert np.all(values>0) and np.all(np.isfinite(values))
    buf=b"".join(values[ref[q][-1]].astype("<f8",copy=False).tobytes() for q in sorted(ref))
    p=D/f"utility-{seed}.f64.gz"
    p.write_bytes(gzip.compress(buf,mtime=0,compresslevel=4))
    receipts[str(seed)]={"candidates":len(values),"utility":sha(p)}
    print("original binary64",seed,len(values),flush=True)
put(D/"original_receipt.json",receipts)

