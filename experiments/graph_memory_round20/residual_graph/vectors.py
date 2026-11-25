"""Two isolated encoder views of exact strings. Base is used only for mining negatives."""
from setup_graph import ROOT,RUN,TR,TRAINED,R18,CACHE,pilot,load,put,h
import json,sys,time,sqlite3
import numpy as np
def database():
    c=sqlite3.connect(RUN/'vectors.sqlite3',uri=True,timeout=120)
    c.execute('pragma journal_mode=WAL')
    c.execute('create table if not exists corpus(k blob primary key,txt text,n int,base int,dev int) without rowid')
    c.execute('create table if not exists vectors(k blob,prec text,v blob,primary key(k,prec)) without rowid')
    return c
def ro(p):return p.resolve().as_uri()+'?mode=ro'
def prepare():
    c=database();t=time.monotonic();started=0
    for i in range(8):
        if not (RUN/f'graphs-{i}.json').exists():raise RuntimeError(f'shard {i} not ready')
        c.execute('attach database ? as sh',[ro(RUN/f'strings{i}.sqlite')])
        c.execute('insert into corpus select k,txt,n,base,0 from sh.x where true on conflict(k) do update set base=max(base,excluded.base)');c.commit();c.execute('detach sh')
    dev=set()
    for f in (TRAINED/'projection/dev').glob('*.json.gz'):
        j=load(f)
        dev.update(h('passage: '+v['text']) for v in j['pool']);dev.update(h('query: '+q['text']) for q in j['qs'])
    c.executemany('update corpus set dev=1 where k=?',[(k,) for k in dev]);c.commit()
    facts={}
    imports=[('r19ft',TRAINED/'trained-vectors.sqlite3',"select v.k,'ft',v.v from sh.vectors v join corpus c on v.k=c.k where v.prec='fp32'"),
             ('bounded_ft',TRAINED.parent/'x20-isetrace-bounded-dense/blocks.sqlite3',"select v.k,'ft',v.v from sh.vectors v join corpus c on v.k=c.k"),
             ('r18_base',CACHE/'vectors.sqlite3',"select v.k,'base',v.v from sh.vectors v join corpus c on v.k=c.k where v.prec='fp32' and c.base=1")]
    for name,p,sql in imports:
        c.execute('attach database ? as sh',[ro(p)]);before=c.total_changes;c.execute('insert or ignore into vectors '+sql);facts[name]=c.total_changes-before;c.commit();c.execute('detach sh')
    total,base,devcount=c.execute('select count(*),sum(base),sum(dev) from corpus').fetchone()
    assert total==load(TR/'rgcn-feasibility.json')['all_splits_unique'] and devcount==len(dev)
    cfg=dict(FT=pilot.sha(TRAINED/'model/model.safetensors'),BASE=pilot.sha(pilot.CACHE.parent/'e5-base-v2/model.safetensors'),unique=total,base_required=base,dev_selected=devcount,copied=facts,seconds=time.monotonic()-t,
             inputs={f.name:pilot.sha(f) for f in sorted(RUN.glob('graphs-*.json'))},protocol=pilot.sha(ROOT/'protocol-lock.json'),code=pilot.sha(ROOT/'vectors.py'))
    put(ROOT/'vectors-plan.json',cfg);print(cfg,flush=True)
def encode(mode):
    import torch
    from train import pin
    from graph_memory.embeddings import load_sentence_transformer
    pin();plan=load(ROOT/'vectors-plan.json');assert plan['code']==pilot.sha(ROOT/'vectors.py')
    p=TRAINED/'model' if mode in ['dev','ft'] else pilot.CACHE.parent/'e5-base-v2'
    assert plan['BASE' if mode=='base' else 'FT']==pilot.sha(p/'model.safetensors')
    m=load_sentence_transformer(str(p),device='cuda').eval();c=database();prec='base' if mode=='base' else 'ft'
    filt={'dev':'dev=1','base':'base=1','ft':'true'}[mode]
    sql=f'select k,txt from corpus s where {filt} and not exists(select 1 from vectors v where v.k=s.k and v.prec=?) order by n,k'
    cur=c.execute(sql,[prec]);t=time.monotonic();nr=0;nt=0
    with torch.inference_mode():
        while batch:=cur.fetchmany(512):
            ss=[s for _,s in batch];v=m.encode(ss,batch_size=64,normalize_embeddings=True,show_progress_bar=False)
            assert v.shape==(len(ss),768) and v.dtype==np.float32 and np.isfinite(v).all()
            nt+=sum(m.tokenizer(ss,truncation=True,max_length=m.max_seq_length,return_length=True)['length'])
            c.executemany('insert into vectors values(?,?,?)',[(k,prec,a.astype('<f4',copy=False).tobytes()) for (k,_),a in zip(batch,v,strict=True)])
            c.commit();nr+=len(ss)
            if nr%8192==0 or len(ss)<512:print(mode,nr,nt,round(time.monotonic()-t,1),flush=True)
    actual=c.execute(f'select count(*) from corpus s join vectors v using(k) where v.prec=? and {filt}',[prec]).fetchone()[0]
    assert actual=={'dev':plan['dev_selected'],'base':plan['base_required'],'ft':plan['unique']}[mode]
    put(ROOT/f'cost-{mode}.json',dict(all=actual,encoded=nr,tokens=nt,seconds=time.monotonic()-t,peak_gpu_bytes=torch.cuda.max_memory_allocated(),device=torch.cuda.get_device_name(),precision='fp32',tf32=False))
if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    else:encode(sys.argv[1])

