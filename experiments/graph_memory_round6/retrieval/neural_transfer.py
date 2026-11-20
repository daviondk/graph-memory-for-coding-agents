"""Prepare blinded Python packets then run the previously audited publisher UniXcoder wrapper on CPU."""
import gzip,hashlib,json,sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1];E=W/'graph_memory_round4/encoder';R5=W/'graph_memory_round5/retrieval'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def save(n,v):(D/n).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf8')
def put(n,v):
    with gzip.open(D/n,'wt',encoding='utf8') as f:
        for x in v:f.write(json.dumps(x,separators=(',',':'))+'\n')
def load(p):return json.loads(Path(p).read_bytes())
def prepare():
    import pyarrow.parquet as pq
    plan=load(D/'roster.json')
    fresh={Path(p):m['fresh'] for p,m in plan.items() if 'fresh' in m}
    hard={p.stem.split('_')[1]:len(inds) for p,inds in fresh.items() if '_hard_' in p.name}
    data=[]
    for p,inds in fresh.items():
        selected=dict(inds)
        if '_easy_' in p.name:
            chosen=sorted(selected,key=lambda i:digest(f'R6-encoder|{p.stem}|{i}'))[:hard[p.stem.split('_')[1]]]
            selected={i:selected[i] for i in chosen}
        off=0
        for batch in pq.ParquetFile(p).iter_batches(batch_size=32,columns=['code','context','repo_name']):
            for j,r in enumerate(batch.to_pylist(),off):
                if j in selected:
                    q='\n'.join(r['code'].splitlines()[-3:])
                    data.append(dict(panel=p.stem.rsplit('_',1)[0],idx=selected[j],project=r['repo_name'],queries={'3':q},candidates=r['context']))
            off+=len(batch)
    put('blind_new.jsonl.gz',data)
    save('data_lock.json',dict(utc=datetime.now(timezone.utc).isoformat(),n=len(data),cases=sorted([r['panel'],r['idx']] for r in data),
         blind=sha(D/'blind_new.jsonl.gz'),source=sha(D/'neural_transfer.py'),protocol=sha(D/'ENCODER_ADDENDUM_RU.md'),
         encoder=sha(R5/'embed.py'),wrapper=sha(E/'repo_unixcoder.py'),actual_threads=3))
def infer():
    sys.path.insert(0,str(R5))
    import embed
    # Keep the exact inference algorithm. Redirect all inputs/outputs to the R6 workspace.
    embed.D=D;embed.E=E;embed.jsonrows=put;embed.dump=save
    embed.torch.set_num_threads(3)
    embed.main()
    r=load(D/'encoder_receipt.json')
    # In the inherited report the 'threads' field is the R5 constant.
    r['threads']=embed.torch.get_num_threads();save('encoder_receipt.json',r)
if __name__=='__main__':
    {'prepare':prepare,'infer':infer}[sys.argv[1]]()
