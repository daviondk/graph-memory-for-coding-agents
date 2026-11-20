"""Use the exact RepoBench archive crop, replay cached embeddings' orders only for identical queries."""
import gzip,json,sys
from pathlib import Path
D=Path(__file__).resolve().parent;A=D/'author';W=D.parents[1];E=W/'graph_memory_round4/encoder';R5=W/'graph_memory_round5/retrieval'
def prepare():
    from run import R,load,now,panel_name,rows,save,sha,writegz,digest,author_function,Adapter,readgz
    import numpy as np
    import pickle
    from memory import features,encode
    from field_model import make
    from native_run import load_module
    A.mkdir(exist_ok=True)
    crop=author_function('repo_author_utils.py','crop_code_lines')
    jacc=author_function('repo_author_similarity.py','jaccard_similarity');tok=Adapter()
    load_module('common','publisher_common.py');load_module('arms','publisher_arms.py');pub=load_module('repobench','publisher_repobench.py')
    w=pickle.loads((D/'models.pkl').read_bytes())['full']
    base=pickle.loads((R/'models.pkl').read_bytes())[3,'graph']
    selected={(p,j) for p,j in load(D/'data_lock.json')['cases']}
    old_orders={(r['panel'],r['idx']):r['rank'] for r in readgz(D/'new_encoder.jsonl.gz')}
    for r in readgz(D/'decisions.jsonl.gz'):
        if r['stage']=='archive':old_orders[r['panel'],r['idx']]=r['orders']['r5_unix']
    cases=[]; packets=[]; allx=[];offset=[0]
    source_archive={(p,i):(h,a['jaccard'],a['graph']) for p,i,pr,h,a in readgz(R/'archive.pred.jsonl.gz') if (p,i) in old_orders}
    for path,spec in load(D/'roster.json').items():
        p=Path(path);pn=panel_name(p.stem)
        if 'archive' in spec:sel=dict(spec['archive'])
        elif 'fresh' in spec:sel={i:k for i,k in spec['fresh'] if (pn,k) in selected}
        else:continue
        for j,r in enumerate(rows(p,['repo_name','code','context'])):
            if j not in sel:continue
            k=sel[j];key=pn,k;docs=r['context'];q=crop(r['code'],3);old='\n'.join(r['code'].splitlines()[-3:]);n=len(docs)
            x=features(q,encode(docs),3)
            direct,links=make(q,docs);allx.append(np.column_stack([x,direct,links]));offset.append(offset[-1]+n)
            orders={'bm25':pub.bm25_rank(q,docs),'jaccard':sorted(range(n),key=lambda i:jacc(q,docs[i],tok),reverse=True)}
            if old==q:orders['unix']=old_orders[key]
            else:packets.append(dict(panel=pn,idx=k,project=r['repo_name'],candidates=docs,queries={'3':q}))
            if 'archive' in spec:
                h,jac,gr=source_archive[key];assert h==digest(q) and jac==orders['jaccard']
            cases.append(dict(panel=pn,idx=k,project=r['repo_name'],changed=old!=q,n=n,query_sha=digest(q),orders=orders))
    matrix=np.concatenate(allx)
    ref=base.predict_proba(matrix[:,:43])[:,1];ranker=w.predict_proba(matrix)[:,1]
    for r,lo,hi in zip(cases,offset[:-1],offset[1:]):
        for name,v in [('r4',ref),('full',ranker)]:r['orders'][name]=np.argsort(-v[lo:hi],kind='stable').tolist()
        if r['panel'].startswith('java'):assert source_archive[r['panel'],r['idx']][2]==r['orders']['r4']
    writegz('author/blind_new.jsonl.gz',packets);writegz('author/base_decisions.jsonl.gz',cases)
    save('author/data_lock.json',dict(utc=now(),n=len(cases),to_embed=len(packets),protocol=sha(D/'AUTHOR_CROP_RU.md'),code=sha(D/'author_crop.py'),blind=sha(A/'blind_new.jsonl.gz'),base=sha(A/'base_decisions.jsonl.gz'),archive_jaccard_and_r4_verified=224))
def infer():
    sys.path.insert(0,str(R5))
    import embed
    embed.D=A;embed.E=E
    def put(n,records):
        with gzip.open(A/n,'wt',encoding='utf8') as f:
            for x in records:f.write(json.dumps(x,separators=(',',':'))+'\n')
    def save(n,v):(A/n).write_text(json.dumps(v,indent=2),encoding='utf8')
    embed.dump=save;embed.jsonrows=put;embed.torch.set_num_threads(4)
    embed.main()
    r=json.loads((A/'encoder_receipt.json').read_bytes());r['threads']=embed.torch.get_num_threads();save('encoder_receipt.json',r)
if __name__=='__main__':{'prepare':prepare,'infer':infer}[sys.argv[1]]()
