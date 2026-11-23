"""Frozen native SentenceTransformer with an external, exact-input cache."""
import contextlib, hashlib, json, os, sys, time
import numpy as np
import torch, transformers,sentence_transformers
from inventory import ROOT,CACHE,W,load,put,db,pilot
from graph_memory.embeddings import load_sentence_transformer
torch.backends.cuda.matmul.allow_tf32=False
torch.backends.cudnn.allow_tf32=False
torch.set_num_threads(2)
def getmodel():
    assert torch.cuda.is_available()
    for r in load(ROOT/'inventory.json')['weights']:assert pilot.sha(W/r['path'])==r['sha256']
    return load_sentence_transformer(str(W),device='cuda').eval()
def encode(m,texts,prec):
    ctx=torch.autocast('cuda',dtype=torch.float16) if prec=='mixed' else contextlib.nullcontext()
    with torch.inference_mode(),ctx:
        out=m.encode(texts,batch_size=64,normalize_embeddings=True,show_progress_bar=False)
    return np.asarray(out,dtype='<f4')
def bench():
    model=getmodel();con=db();n=load(ROOT/'inventory.json')['unique_prefixed_strings']
    rows=con.execute('select text from corpus order by k limit 512').fetchall()
    ss=[r[0] for r in rows];out={}
    for p in ['mixed','fp32']:
        encode(model,ss[:64],p)
        s=time.perf_counter();z=encode(model,ss,p);torch.cuda.synchronize()
        sec=time.perf_counter()-s
        assert z.shape==(len(ss),768)
        out[p]=dict(seconds=sec,n=len(ss),strings_per_second=len(ss)/sec,full_estimated_minutes=n*sec/len(ss)/60)
        print(p,out[p],flush=True)
    primary='fp32' if out['fp32']['full_estimated_minutes']<=45 else 'mixed'
    put(ROOT/'throughput.json',dict(samples=out,primary_precision=primary,n=n,gpu=torch.cuda.get_device_name(0),torch=torch.__version__,cuda=torch.version.cuda,
        sentence_transformers=sentence_transformers.__version__,transformers=transformers.__version__,max_seq_length=model.max_seq_length,
        model_param_dtype=str(next(model.parameters()).dtype),tf32=False))
def run():
    plan=load(ROOT/'plan-seal.json')
    for n,h in plan.items():assert pilot.sha(ROOT/n)==h
    model=getmodel();con=db();mode=load(ROOT/'throughput.json')['primary_precision']
    for prec,audit in [(mode,False)]+([('fp32',True)] if mode=='mixed' else []):
        sql='select c.k,c.text from corpus c where '+('c.audit=1 and ' if audit else '')+'not exists(select 1 from vectors v where v.prec=? and v.k=c.k) order by c.nchar,c.k'
        cur=con.execute(sql,(prec,));n=0;stamp=time.perf_counter()
        while rows:=cur.fetchmany(512):
            v=encode(model,[r[1] for r in rows],prec);assert np.isfinite(v).all() and v.shape==(len(rows),768)
            con.executemany('insert into vectors values(?,?,?)',[(k,prec,vec.tobytes()) for (k,_),vec in zip(rows,v,strict=True)])
            con.commit();n+=len(rows)
            print(prec,n,round(time.perf_counter()-stamp,2),flush=True)
        put(ROOT/f'cost-{prec}.json',dict(completed_total=con.execute('select count(*) from vectors where prec=?',(prec,)).fetchone()[0],newly_encoded=n,seconds=time.perf_counter()-stamp,
            peak_allocated_gpu_bytes=torch.cuda.max_memory_allocated(),audit_only=audit))
if __name__=='__main__':
    {'bench':bench,'run':run}[sys.argv[1]]()
