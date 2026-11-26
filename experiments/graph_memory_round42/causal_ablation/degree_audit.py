"""Rebuild the first four channels and role ranks from candidate metadata alone."""
from collections import Counter
from scipy.stats import rankdata
import numpy as np
from core42 import D,read,save,sha


def main():
    result={}
    for st in ("train","test"):
        stats=Counter()
        for i in range(8):
            fp=D/f"{st}-{i}.npz";rp=D/f"{st}-{i}.json.gz"
            assert read(D/f"features-{i}-seal.json")["rows"][st]==[sha(rp),sha(fp)]
            with np.load(fp) as a:
                m,e,permuted=a["meta"],a["edge"],a["sham"]
                local=np.column_stack([np.log1p(1-m[:,5]),np.log1p(1-m[:,4]),(1-m[:,0])*m[:,11],m[:,0]*m[:,10]])
                assert np.array_equal(local,e[:,:4])
                pos=0
                for q,t,n,ids in read(rp):
                    sl=slice(pos,pos+n);pos+=n
                    rr=np.zeros((n,4))
                    for role in (0,1):
                        own=np.flatnonzero(m[sl,0]==role)
                        if len(own):
                            rr[own]=(rankdata(local[sl][own],axis=0,method="average")-.5)/len(own)-.5
                    assert np.array_equal(rr,e[sl,8:12])
                    stats["candidate_rows"]+=n;stats["queries"]+=1
                    stats["rows_nonzero_intercall_degree"]+=int(np.any(e[sl,4:8],axis=1).sum())
                    stats["rows_changed_by_sham"]+=int(np.any(e[sl]!=permuted[sl],axis=1).sum())
                    stats["local_decoded_exactly"]+=n
                assert pos==len(m)
        result[st]=dict(stats)
    save(D/"degree-audit.json",dict(counts=result,code=sha(D/"degree_audit.py")))
    print(result)


if __name__=="__main__":main()
