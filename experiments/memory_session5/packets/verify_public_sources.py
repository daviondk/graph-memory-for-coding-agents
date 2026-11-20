"""Optional, read-only reconstruction of all four saved cohorts from the publisher's 8 parquet files."""
import argparse,gzip,hashlib,json
from pathlib import Path
from common import ROOT,rows
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parquet_dir',type=Path,help='Directory containing all tool-xxxxx-of-00008.parquet files from the revision listed in REPRODUCE.md')
    args=parser.parse_args()
    from extract5 import decode,pq
    groups={'source/train':json.loads((ROOT/'selection.json').read_bytes())['train'],'source/test':json.loads((ROOT/'selection.json').read_bytes())['test'],'transfer/source':json.loads((ROOT/'transfer/selection.json').read_bytes()),'allocation/source':json.loads((ROOT/'allocation/selection.json').read_bytes())}
    picks={(k,i):(n,task) for n,g in groups.items() for task,k,i in g};seen=accepted=excluded=0
    for k,desc in enumerate(json.loads((ROOT/'shards.json').read_bytes())):
        path=args.parquet_dir/Path(desc['path']).name
        with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==desc['lfs']['oid']
        streams={n:iter(rows(ROOT/n/f'{k}.jsonl.gz')) for n in groups};idx=0
        with pq.ParquetFile(path) as pf:
            for batch in pf.iter_batches(batch_size=24,columns=['instance_id','traj_id','messages','model'],use_threads=False):
                for j in range(batch.num_rows):
                    if (k,idx) in picks:
                        n,task=picks[k,idx];rec=batch.slice(j,1).to_pylist()[0]
                        assert rec['instance_id']==task;obj=decode(rec,k,idx);seen+=1
                        if obj is None:excluded+=1
                        else:assert obj==next(streams[n]);accepted+=1
                    idx+=1
        assert all(next(it,None) is None for it in streams.values());print(k,seen,accepted,excluded,flush=True)
    assert seen==sum(map(len,groups.values()))
    print('PASS publisher SHA + every selected trajectory projected correctly',seen,accepted,excluded)
if __name__=='__main__':main()
