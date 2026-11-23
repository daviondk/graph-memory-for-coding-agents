"""Frozen fine-tuned E5 embeddings of exact retained slices; identical read budgets."""
from collections import defaultdict
import hashlib,json,sys,time
import numpy as np
from inputs import ROOT,RUN,ARMS,db,key,load,put,pilot,TR
from graph_memory.text.tokens import content_tokens
from rank_bm25 import BM25Okapi
def lock():
    ix=load(ROOT/'index-plan.json');assert ix['protocol']==pilot.sha(ROOT/'PROTOCOL_RU.md')
    put(ROOT/'reader-plan.json',dict(files={n:pilot.sha(ROOT/n) for n in ['PROTOCOL_RU.md','inputs.py','index-plan.json','retrieve_blocks.py']},checkpoint=pilot.sha(TR/'trained-checkpoint.json'),weight=load(TR/'trained-checkpoint.json')['files']['model.safetensors'],precision='FP32 with TF32 disabled',fusion_k=60))
def encode():
    import torch
    from graph_memory.embeddings import load_sentence_transformer
    from train import pin
    pin();plan=load(ROOT/'reader-plan.json');assert all(pilot.sha(ROOT/n)==h for n,h in plan['files'].items())
    from prepare import RUN as trained_run
    assert pilot.sha(trained_run/'model/model.safetensors')==plan['weight']
    m=load_sentence_transformer(str(trained_run/'model'),device='cuda').eval();c=db()
    c.execute('create table if not exists identity(w text primary key)');c.execute('insert or ignore into identity values(?)',[plan['weight']]);c.commit();assert c.execute('select w from identity').fetchall()==[(plan['weight'],)]
    q=c.execute('select i.k,i.txt from inputs i where not exists(select 1 from vectors v where v.k=i.k) order by i.nc,i.k');n=0;st=time.perf_counter();nt=0
    with torch.inference_mode():
        while batch:=q.fetchmany(512):
            ss=[t for k,t in batch];v=m.encode(ss,batch_size=64,normalize_embeddings=True,show_progress_bar=False)
            assert v.shape==(len(ss),768) and v.dtype==np.float32 and np.isfinite(v).all()
            nt+=sum(m.tokenizer(ss,truncation=True,max_length=m.max_seq_length,return_length=True)['length'])
            c.executemany('insert into vectors values(?,?)',[(k,x.astype('<f4',copy=False).tobytes()) for (k,s),x in zip(batch,v,strict=True)]);c.commit();n+=len(ss)
            if n%8192==0 or len(ss)<512:print(n,round(time.perf_counter()-st,1),flush=True)
    total=c.execute('select count(*) from vectors').fetchone()[0];assert total==load(ROOT/'index-plan.json')['unique_strings']
    put(ROOT/'encoding-cost.json',dict(unique=total,new=n,seconds=time.perf_counter()-st,exact_unpadded_model_tokens=nt,fp32_vector_bytes=total*3072,peak_torch_gib=torch.cuda.max_memory_allocated()/2**30))
def read(ids,cost):
    result=[];n=0
    for j in ids:
        if n+cost[j]<=2048:result.append(j);n+=cost[j]
    return result
def fetch(c,keys):
    ans={}
    for pos in range(0,len(keys),512):
        current=keys[pos:pos+512];marks=','.join('?' for _ in current)
        for k,v,s in c.execute('select i.k,v.v,i.txt from inputs i join vectors v using(k) where i.k in ('+marks+')',current):ans[k.hex()]=(np.frombuffer(v,dtype='<f4'),s)
    return ans
def forecasts():
    c=db();f={};plan=load(ROOT/'reader-plan.json');assert all(pilot.sha(ROOT/k)==h for k,h in plan['files'].items())
    ix=load(ROOT/'index-plan.json')
    for stage in ('test','dev'):
        count=0
        for i in range(8):
            name=f'cards-{stage}-{i}.json.gz';assert pilot.sha(RUN/name)==ix['inputs'][name]
            result=[]
            for row in load(RUN/name):
                meta={int(j):v for j,v in row['b'].items()};cost={j:v[4] for j,v in meta.items()}
                keys=sorted({bytes.fromhex(m[6]) for m in meta.values()}|{bytes.fromhex(k) for _,k in row['q']});values=fetch(c,keys);assert len(values)==len(keys)
                groups={}
                for a in ARMS:
                    retained=row['k'][a];lex=[content_tokens(values[meta[j][6]][1][9:]) for j in retained]
                    assert all(values[meta[j][6]][1].startswith('passage: ') for j in retained)
                    bm=BM25Okapi(lex) if any(lex) else None
                    matrix=np.array([values[meta[j][6]][0] for j in retained],dtype=np.float64)
                    if not retained:matrix=np.empty((0,768),dtype=np.float64)
                    per={}
                    for q,kh in row['q']:
                        qv,qt=values[kh];assert qt.startswith('query: ')
                        sb=bm.get_scores(content_tokens(qt[7:])) if bm else [0.]*len(retained)
                        sd=matrix@qv.astype(np.float64)
                        br=[retained[j] for j in sorted(range(len(retained)),key=lambda j:(-sb[j],retained[j]))]
                        dr=[retained[j] for j in sorted(range(len(retained)),key=lambda j:(-sd[j],retained[j]))]
                        assert read(br,cost)==row['bm'][a][q],(stage,a,q)
                        B={k:j for j,k in enumerate(br,1)};D={k:j for j,k in enumerate(dr,1)}
                        fr=sorted(retained,key=lambda j:(-(1/(60+B[j])+1/(60+D[j])),j))
                        per[q]={name:read(order,cost) for name,order in [('bm25',br),('dense',dr),('rrf60',fr)]}
                    groups[a]=dict(k=retained,per=per)
                result.append(dict(t=row['t'],b={j:v[:6] for j,v in meta.items()},arms=groups))
                count+=len(row['q'])
            n=f'forecasts-{stage}-{i}.json.gz';put(ROOT/n,result);f[n]=pilot.sha(ROOT/n)
        assert count==ix['n_queries'][stage];print(stage,count,flush=True)
    put(ROOT/'forecast-seal.json',dict(plan=pilot.sha(ROOT/'reader-plan.json'),forecasts=f))
if __name__=='__main__':{'plan':lock,'encode':encode,'predict':forecasts}[sys.argv[1]]()
