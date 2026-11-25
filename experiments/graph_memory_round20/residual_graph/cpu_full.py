"""Resume all remaining FP32 encoder inputs transactionally. Share CPU with active fallback panels."""
from pathlib import Path
import sys,time,hashlib,json,os
import numpy as np,torch
from setup_graph import ROOT,RUN,TRAINED,pilot,put,load,h
from vectors import database
from graph_memory.embeddings import load_sentence_transformer
from datetime import datetime,timezone
def reserve():
    from data import graphfiles
    allc=load(ROOT/'cpu_fallback/cohorts.json');tids={t for x in allc.values() for t in x['t']};out=set()
    for t in tids:
        p,sha=graphfiles()[t];r=load(p);out.update(h('passage: '+v['text']) for v in r['g']['nodes']);out.update(h('query: '+text) for _,text in r['q'])
    return out
def main():
    c=database();reserved=reserve();slow,fast=2,8
    torch.set_num_threads(slow);plan=load(ROOT/'vectors-plan.json')
    # Persist progress every 32 texts; only canonical FP32 tensors enter this table.
    log=RUN/'logs/full-cpu.progress.jsonl';pending_fallback=ROOT/'cpu_fallback/hash64/cpu-encoding.json'
    cuda_signal=RUN/'yield-cpu-full';limit='base=1'
    for m in ['ft','base']:
        p=TRAINED/'model' if m=='ft' else pilot.CACHE.parent/'e5-base-v2';assert pilot.sha(p/'model.safetensors')==plan['FT' if m=='ft' else 'BASE']
        encoder=load_sentence_transformer(str(p),device='cpu').eval();threads=slow
        sql="select s.k,s.txt from corpus s where "+('true' if m=='ft' else limit)+" and not exists(select 1 from vectors v where v.k=s.k and v.prec=?) order by s.n,s.k"
        while True:
            num=0
            with torch.inference_mode():
                pending=[k for k, in c.execute(sql.replace('s.k,s.txt','s.k'),[m])]
                for index in range(0,len(pending),32):
                    ks=pending[index:index+32];marks=','.join('?' for k in ks)
                    available={k:s for k,s in c.execute('select k,txt from corpus where k in ('+marks+')',ks)}
                    batch=[(k,available[k]) for k in ks]
                    if cuda_signal.exists():print('CPU worker yielded on explicit flag',flush=True);return
                    if not pending_fallback.exists():batch=[row for row in batch if row[0] not in reserved]
                    if not batch:continue
                    if (ROOT/'cpu_fallback/hash64/results.json').exists() and threads!=fast:
                        torch.set_num_threads(fast);threads=fast
                    start=time.monotonic();ss=[s for k,s in batch]
                    v=encoder.encode(ss,batch_size=4 if threads==slow else 8,normalize_embeddings=True,show_progress_bar=False)
                    assert v.shape==(len(ss),768) and v.dtype==np.float32 and np.isfinite(v).all()
                    n=sum(encoder.tokenizer(ss,truncation=True,max_length=encoder.max_seq_length,return_length=True)['length'])
                    before=c.total_changes;c.executemany('insert or ignore into vectors values(?,?,?)',[(k,m,x.astype('<f4',copy=False).tobytes()) for (k,_),x in zip(batch,v,strict=True)]);c.commit();added=c.total_changes-before;num+=added
                    with log.open('a',encoding='utf8') as fd:fd.write(json.dumps(dict(mode=m,count=len(ss),inserted=added,model_tokens=n,seconds=time.monotonic()-start,threads=threads,first_key=batch[0][0].hex(),last_key=batch[-1][0].hex(),finished=datetime.now(timezone.utc).isoformat()))+'\n')
                    if num and num%1024==0:print(m,num,threads,flush=True)
            remaining=c.execute("select count(*) from corpus s where "+('true' if m=='ft' else limit)+" and not exists(select 1 from vectors v where v.k=s.k and v.prec=?)",[m]).fetchone()[0]
            if not remaining:break
            if not num:time.sleep(5)
        print('full coverage',m,flush=True)
    put(ROOT/'full-cpu-complete.json',dict(ft=c.execute("select count(*) from vectors where prec='ft'").fetchone()[0],base=c.execute("select count(*) from vectors where prec='base'").fetchone()[0],progress_sha=pilot.sha(log)))
if __name__=='__main__':main()

