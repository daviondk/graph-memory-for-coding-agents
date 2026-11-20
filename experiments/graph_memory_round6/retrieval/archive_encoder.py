"""Actual UniXcoder on a project-capped subpanel of the independent academic Python archive."""
import gzip,json,sys
from collections import Counter
from pathlib import Path
D=Path(__file__).resolve().parent
A=D/'replication/encoder';W=D.parents[1];R5=W/'graph_memory_round5/retrieval';E=W/'graph_memory_round4/encoder'
def prepare():
    from run import author_function,load,now,save,sha,rows,digest,writegz
    import pyarrow.parquet as pq
    A.mkdir(parents=True,exist_ok=True)
    crop=author_function('repo_author_utils.py','crop_code_lines')
    inputs=[]
    for panel,ids in load(A.parent/'roster.json').items():
        p=A.parent/(panel+'.parquet');names=pq.read_table(p,columns=['repo_name']).column(0)
        chosen=set();nrepo=Counter()
        for i in sorted(ids,key=lambda i:digest(f'R6-archive-neural|{panel}|{i}')):
            repo=names[i].as_py()
            if nrepo[repo]>=2:continue
            chosen.add(i);nrepo[repo]+=1
            if len(chosen)==32:break
        for j,r in enumerate(rows(p,['code','context','repo_name'])):
            if j in chosen:inputs.append(dict(panel=panel,idx=j,project=r['repo_name'],candidates=r['context'],queries={'3':crop(r['code'],3)}))
    writegz('replication/encoder/blind_new.jsonl.gz',inputs)
    save('replication/encoder/data_lock.json',dict(utc=now(),n=len(inputs),blind=sha(A/'blind_new.jsonl.gz'),
         author_protocol=sha(D/'ARCHIVE_ENCODER_RU.md'),code=sha(D/'archive_encoder.py'),weights=sha(E/'weights/pytorch_model.bin'),
         sampling=sha(A.parent/'roster.json')))
def infer():
    sys.path.insert(0,str(R5))
    import embed
    embed.D=A;embed.E=E
    def output(n,recs):
        with gzip.open(A/n,'wt',encoding='utf8') as f:
            for x in recs:f.write(json.dumps(x,separators=(',',':'))+'\n')
    def save(n,v):(A/n).write_text(json.dumps(v,indent=2),encoding='utf8')
    embed.dump=save;embed.jsonrows=output;embed.torch.set_num_threads(4)
    embed.main()
    receipt=json.loads((A/'encoder_receipt.json').read_bytes());receipt['threads']=4;save('encoder_receipt.json',receipt)
def grade():
    from run import load,now,readgz,save,sha,writegz
    from grade import stats
    pred=load(A/'encoder_receipt.json')
    assert sha(A/'new_encoder.jsonl.gz')==pred['pred']
    existing={(r['panel'],r['idx']):r for r in readgz(A.parent/'pairs.jsonl.gz')}
    out=[]
    for v in readgz(A/'new_encoder.jsonl.gz'):
        r=existing[v['panel'],v['idx']];assert sorted(v['rank'])==list(range(r['n']))
        o=dict(r,ranks=dict(r['ranks'],unix=v['rank'].index(r['gold'])+1 if r['gold'] in v['rank'] else None))
        out.append(o)
    writegz('replication/encoder/pairs.jsonl.gz',out)
    asref=[dict(r,ranks=dict(r['ranks'],full=r['ranks']['alignment'],original_full=r['ranks']['full'])) for r in out]
    save('replication/encoder/results.json',dict(utc=now(),raw=stats(out),alignment=stats(asref),
         hard_alignment=stats([r for r in asref if r['panel'].endswith('hard')]),pair_hash=sha(A/'pairs.jsonl.gz')))
if __name__=='__main__':{'prepare':prepare,'infer':infer,'grade':grade}[sys.argv[1]]()
