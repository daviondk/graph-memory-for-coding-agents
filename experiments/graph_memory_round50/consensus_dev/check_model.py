"""Independent R39 Python tree traversal and frozen projection on all five development ranks."""
import os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
import gzip,sys
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(W/"graph_memory_round39/global_packet"))
import packet
read,sha,put=packet.read,packet.sha,packet.save
def main():
    tag=read(D/"input-seal.json");model=read(W/"graph_memory_round39/global_packet/models.json")["models"]["graph"]
    rows=read(W.parents[1]/"x20-r33-budget-loss/dev.json.gz");rows.sort(key=lambda r:r["q"])
    m0=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"]
    audit={}
    for s in (13,17,29,37,41):
        m=m0 if s==13 else read(W/f"graph_memory_round21/five_seed/seed-{s}/calibration.json")["rank"]
        ranks=read(D/f"ranks-{s}.json.gz");buf=D/f"utility-{s}.f64.gz";assert sha(buf)==tag["files"][buf.name]
        encoded=np.frombuffer(gzip.decompress(buf.read_bytes()),dtype="<f8")
        blocks=[]
        for r in rows:
            dense=ranks[r["q"]][0]
            z=np.asarray(r["x"]);n=len(dense);rx=packet.base.rankx(n)
            g=np.asarray(r["o"])-packet.base.linear(m0,rx)
            rr=np.empty(n);rr[dense]=packet.base.linear(m,rx)
            z[dense,0]=np.log1p(np.arange(1,n+1));x,_=packet.feature(z,g,rr)
            blocks.append(x)
        gu=np.logaddexp(0,packet.portable(model,np.vstack(blocks)))
        assert np.array_equal(gu,encoded),(s,float(np.max(np.abs(gu-encoded))))
        audit[s]=len(gu)
    put(D/"tree-crosscheck.json",dict(exact_per_seed=audit,source=sha(Path(__file__)),upstream=sha(W/"graph_memory_round39/global_packet/packet.py"),trained_queries=3894))
    print(audit)
if __name__=="__main__":main()

