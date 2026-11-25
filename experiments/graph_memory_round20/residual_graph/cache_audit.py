"""Inspect checkpoints of reused stores and rerun a pinned sample of embeddings on CPU."""
import hashlib,sqlite3,sys,time
import numpy as np
from setup_graph import ROOT,RUN,TR,TRAINED,R18,CACHE,pilot,load,put
from vectors import database,ro
def sources():
    c=database();current=load(ROOT/'vectors-plan.json');res={}
    assert current['FT']==pilot.sha(TRAINED/'model/model.safetensors')==load(TR/'trained-checkpoint.json')['files']['model.safetensors']
    items=[('r19ft',TRAINED/'trained-vectors.sqlite3',"select checkpoint from sh.identity",'ft','v.prec=? and s.prec=?',('fp32','ft')),
           ('bounded_ft',TRAINED.parent/'x20-isetrace-bounded-dense/blocks.sqlite3',"select w from sh.identity",'ft','s.prec=?',('ft',)),
           ('r18_base',CACHE/'vectors.sqlite3',None,'base','v.prec=? and s.prec=?',('fp32','base'))]
    for name,p,ids,kind,filt,args in items:
        c.execute('attach database ? as sh',[ro(p)])
        if ids:assert c.execute(ids).fetchall()==[(current['FT'],)]
        count=equal=close=0;mx=0.;mincos=1.;agg=hashlib.sha256()
        cur=c.execute('select s.k,s.v,v.v from vectors s join sh.vectors v using(k) where '+filt+' order by s.k',args)
        while rows:=cur.fetchmany(256):
            for k,x,y in rows:
                count+=1
                if x==y:equal+=1
                else:
                    a=np.frombuffer(x,dtype='<f4');b=np.frombuffer(y,dtype='<f4');d=float(abs(a-b).max());mx=max(mx,d)
                    co=float(a.astype('float64')@b.astype('float64'));mincos=min(mincos,co)
                    if d<.001 and co>.99999:close+=1
                agg.update(k)
        assert count==equal+close
        if name=='r19ft':assert count==current['copied']['r19ft'] and equal==count
        if name=='r18_base':assert count==current['copied']['r18_base'] and equal==count
        res[name]=dict(intersection=count,byte_equal=equal,close_fp32_under_different_batching=close,max_element_difference=mx,min_dot_over_differences=mincos,key_sha=agg.hexdigest(),verified_model_identity=current['FT'] if ids else current['BASE'])
        c.execute('detach sh')
    put(ROOT/'source-cache-audit.json',res)
def direct():
    from graph_memory.embeddings import load_sentence_transformer
    import torch
    torch.set_num_threads(3);c=database();details={};t=time.monotonic()
    for m,p in [('ft',TRAINED/'model'),('base',pilot.CACHE.parent/'e5-base-v2')]:
        model=load_sentence_transformer(str(p),device='cpu').eval()
        rows=c.execute('select s.k,s.txt,v.v from corpus s join vectors v on s.k=v.k where v.prec=? order by s.k limit 12',[m]).fetchall()
        assert len(rows)==12
        with torch.inference_mode():
            x=model.encode([s for _,s,_ in rows],batch_size=4,normalize_embeddings=True,show_progress_bar=False)
        note=[]
        for a,(k,s,bts) in zip(x,rows,strict=True):
            b=np.frombuffer(bts,dtype='<f4');d=float(abs(a-b).max());dot=float(a.astype('float64')@b.astype('float64'))
            assert d<.001 and dot>.99999
            note.append(dict(key=k.hex(),input_chars=len(s),max_abs_difference=d,dot=dot))
        details[m]=note
    put(ROOT/'direct-embedding-audit.json',dict(samples=details,seconds=time.monotonic()-t,device='cpu',dtype='float32',limit=12,rule='lowest SHA-256 among all required inputs for each encoder'))
if __name__=='__main__':{'sources':sources,'direct':direct}[sys.argv[1]]()

