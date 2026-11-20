from collections import Counter
from common5 import *
import pyarrow.parquet as pq
def main():
    train={r["project"] for r in rr(E/'blind.jsonl.gz')}
    requests=[];sums={};selected={}
    for path in sorted((R/'archive_inputs').glob('*.parquet')):
        panel=path.stem.rsplit('_',1)[0];names=pq.read_table(path,columns=['repo_name']).column(0).to_pylist()
        nc=Counter();ids=set()
        for j in sorted(range(len(names)),key=lambda j:sha(f'R5-routing-v1|{panel}|{j}')):
            p=names[j]
            if p in train or nc[p]>=4:continue
            ids.add(j);nc[p]+=1
            if len(ids)==56:break
        assert len(ids)==56
        selected[panel]=sorted(ids)
        pf=pq.ParquetFile(path);offset=0
        for batch in pf.iter_batches(batch_size=32,columns=['repo_name','context','code']):
            for i in sorted(x for x in ids if offset<=x<offset+len(batch)):
                row=batch.slice(i-offset,1).to_pylist()[0]
                requests.append(dict(panel=panel,idx=i,project=row["repo_name"],candidates=row["context"],queries={str(k):'\n'.join(row["code"].splitlines()[-k:]) for k in (3,10)}))
            offset+=len(batch)
        sums[path.name]=filehash(path)
    jsonrows("blind_new.jsonl.gz",requests)
    dump("roster.json",selected);dump("data_lock.json",dict(utc=now(),n=len(requests),projects=len({r["project"] for r in requests}),target_overlap=0,inputs=sums,blind=filehash(D/'blind_new.jsonl.gz'),protocol=filehash(D/'PROTOCOL_RU.md'),n_cand=sum(len(r['candidates']) for r in requests)))
if __name__=='__main__':main()

