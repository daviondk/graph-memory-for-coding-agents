"""Source-only trained ranking over every official test query and deterministic packing."""
from pathlib import Path
import hashlib,sqlite3,sys,time
import numpy as np
from prepare import ROOT,RUN,R18,pilot,load,put
from project import CACHE,reqs,rank
from forecasts import Lookup
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever
def conn():
    c=sqlite3.connect(RUN/'trained-vectors.sqlite3',timeout=90)
    c.execute('pragma journal_mode=WAL');c.execute('create table if not exists vectors(k blob,prec text,v blob,primary key(k,prec)) without rowid');return c
def lock():
    model=load(ROOT/'trained-checkpoint.json');assert all(pilot.sha(RUN/'model'/f)==h for f,h in model['files'].items())
    put(ROOT/'prediction-plan.json',dict(files={n:pilot.sha(ROOT/n) for n in ('PROTOCOL_RU.md','protocol-seal.json','split.json.gz','trained-checkpoint.json','test_retrieval.py','training-lock.json')},
         frozen_input_inventory=pilot.sha(R18/'isetrace_e5/inventory.json'),old_source_forecasts=pilot.sha(R18/'isetrace_e5/forecast-seal.json'),
         weights_sha256=model['files'].get('model.safetensors',model['files'].get('pytorch_model.bin')),precision='fp32',tf32=False))
def embed():
    import torch
    from train import pin
    from graph_memory.embeddings import load_sentence_transformer
    pin();m=load_sentence_transformer(str(RUN/'model'),device='cuda').eval()
    plan=load(ROOT/'prediction-plan.json');assert all(pilot.sha(ROOT/f)==h for f,h in plan['files'].items())
    precision='fp32';con=conn();con.execute('create table if not exists identity(checkpoint text not null primary key)')
    w=plan['weights_sha256'];assert w
    con.execute('insert or ignore into identity values(?)',[w]);con.commit();assert con.execute('select checkpoint from identity').fetchall()==[(w,)]
    orig=(CACHE/'vectors.sqlite3').resolve().as_uri()+'?mode=ro';con.execute('attach database ? as frozen',[orig])
    sql='select s.k,s.text from frozen.corpus s where not exists(select 1 from main.vectors v where v.k=s.k and v.prec=?) order by s.nchar,s.k'
    cur=con.execute(sql,[precision]);n=0;start=time.monotonic()
    with torch.inference_mode():
        while batch:=cur.fetchmany(512):
            ss=[s for _,s in batch];vs=m.encode(ss,batch_size=64,normalize_embeddings=True,show_progress_bar=False)
            assert vs.shape==(len(ss),768) and vs.dtype==np.float32 and np.isfinite(vs).all()
            con.executemany('insert into vectors values(?,?,?)',[(k,precision,v.astype('<f4',copy=False).tobytes()) for (k,_),v in zip(batch,vs,strict=True)])
            con.commit();n+=len(ss)
            if n%2048==0 or len(ss)<512:print('encoded',n,round(time.monotonic()-start,2),flush=True)
    total=con.execute('select count(*) from vectors').fetchone()[0];assert total==load(R18/'isetrace_e5/inventory.json')['unique_prefixed_strings']
    put(ROOT/'embedding-cost.json',dict(newly_encoded=n,complete=total,seconds=time.monotonic()-start,peak_gpu_bytes=torch.cuda.max_memory_allocated(),dim=768,precision=precision))
def predict():
    plan=load(ROOT/'prediction-plan.json');assert all(pilot.sha(ROOT/f)==h for f,h in plan['files'].items())
    retr=DenseTaskRetriever(model_name=str(RUN/'model'),device='cuda',encoder=Lookup(conn(),'fp32'))
    tok=pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json'));seen=set();dig={};s=time.monotonic()
    for i in range(8):
        output=[]
        for p in sorted((CACHE/'projection').glob(f'{i}-*.json.gz')):
            tr=load(p);requests=reqs(tr);src={c.item_id:c for c in requests[0].candidates};meta={k:c.metadata for k,c in src.items()}
            context=dict(fields=tr['fields'],tokenizer=tok,offset_by_event={})
            for r in requests:
                assert r.task_id not in seen;seen.add(r.task_id)
                rr=pilot.assemble_ranked_result(request=r,method='dense',ranked_nodes=retr.rank(r),top_k=len(src),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
                arms={a:[n.node_id for n in pilot.pack(rr,meta,2048,a)] for a in ('prefix','skip','value','related')}
                extra=rank.clipped(rr,src,pilot.pack(rr,meta,2048,'prefix'),'provenance',context)
                arms['clip']=arms['prefix']+([extra.node_id] if extra is not None else [])
                output.append(dict(q=r.task_id,t=tr['t'],rr=[n.model_dump() for n in rr],partial=extra.model_dump() if extra else None,arms=arms))
        f=f'forecasts-main-{i}.json.gz';put(ROOT/f,output);dig[f]=pilot.sha(ROOT/f);print(i,len(seen),flush=True)
    assert seen=={r['q'] for r in load(ROOT/'split.json.gz')['test']}
    put(ROOT/'forecast-seal.json',dict(plan=pilot.sha(ROOT/'prediction-plan.json'),forecasts=dig,n=len(seen),seconds=time.monotonic()-s))
if __name__=='__main__':{'lock':lock,'embed':embed,'predict':predict}[sys.argv[1]]()
