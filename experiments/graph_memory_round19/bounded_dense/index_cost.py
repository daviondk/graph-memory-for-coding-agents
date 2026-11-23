"""Check exact materialized vectors; physical storage and reusable model files."""
import hashlib,numpy as np
from pathlib import Path
from inputs import ROOT,RUN,TR,db,load,put
def main():
    c=db();n=0;h=hashlib.sha256();mx=0
    cur=c.execute('select v.k,v.v from vectors v order by v.k')
    while rows:=cur.fetchmany(512):
        for k,v in rows:h.update(k);h.update(v)
        arr=np.stack([np.frombuffer(v,dtype='<f4') for _,v in rows])
        assert arr.shape==(len(rows),768) and np.isfinite(arr).all()
        mx=max(mx,float(np.max(np.abs(np.linalg.norm(arr.astype('float64'),axis=1)-1))));n+=len(rows)
    assert n==load(ROOT/'index-plan.json')['unique_strings']
    from prepare import RUN as native
    weights=native/'model';table={f.relative_to(weights).as_posix():f.stat().st_size for f in weights.rglob('*') if f.is_file()}
    page=c.execute('pragma page_size').fetchone()[0];npage=c.execute('pragma page_count').fetchone()[0]
    put(ROOT/'physical-cost.json',dict(unique=n,vector_payload_bytes=n*3072,combined_sqlite_bytes=page*npage,
          combined_db_contents='UTF8 text, SHA strings, all FP32 vectors; research cache shared across 3 policies, 2 splits and questions. SQLite persistent B-tree. Per-agent packed text/vector costs are stored separately.',
          full_checkpoint_bytes=sum(table.values()),checkpoint_files=table,model_sha=load(TR/'trained-checkpoint.json')['files']['model.safetensors'],
          embedding_fingerprint=h.hexdigest(),max_norm_error=mx,vector_dtype='little-endian float32, 768 dimensions'))
if __name__=='__main__':main()
