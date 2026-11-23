"""Stream an exact key/value fingerprint with no public release of raw embeddings."""
import hashlib,sqlite3
import numpy as np
from project import ROOT,CACHE,load,put
def run():
    conn=sqlite3.connect(CACHE/'vectors.sqlite3',timeout=60)
    mode=load(ROOT/'throughput.json')['primary_precision']
    digest=hashlib.sha256();n=0;maxerr=0.
    cur=conn.execute('select k,v from vectors where prec=? order by k',(mode,))
    while rows:=cur.fetchmany(500):
        for k,v in rows:
            assert len(k)==32 and len(v)==768*4
            digest.update(k);digest.update(v)
        mat=np.stack([np.frombuffer(v,dtype='<f4') for _,v in rows]);assert np.isfinite(mat).all()
        n+=len(mat);maxerr=max(maxerr,float(np.max(np.abs(np.linalg.norm(mat.astype(np.float64),axis=1)-1.))))
    assert n==load(ROOT/'inventory.json')['unique_prefixed_strings']
    put(ROOT/'vector-receipt.json',dict(precision=mode,n=n,dim=768,dtype='little-endian float32',max_l2_norm_error=maxerr,
            raw_vector_bytes=n*768*4,sorted_key_plus_vector_bytes_sha256=digest.hexdigest()))
if __name__=='__main__':run()
