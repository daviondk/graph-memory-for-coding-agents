"""Resume the canonical full train after a GPU reset; the model, labels and loss stay fixed."""
from pathlib import Path
import shutil, subprocess
from unittest.mock import patch
import json,sys,time,torch,numpy as np
from setup_graph import ROOT,RUN,TR,TRAINED,pilot,load,put
from vectors import database
from data import split
def costs():
    from recovery_costs import write
    for m in ('ft','base'):
        write(m)

def cpu_fit():
    import fit_graph,train
    saved=fit_graph.train_materialized_graph_retriever
    def run_cpu(**kw):kw['device']='cpu';return saved(**kw)
    def pin_cpu():torch.set_num_threads(8);torch.manual_seed(13)
    with patch.object(fit_graph,'train_materialized_graph_retriever',run_cpu),patch.object(train,'pin',pin_cpu):fit_graph.fit()
def gpu_continue(m):
    from train import pin
    from graph_memory.embeddings import load_sentence_transformer
    pin();assert torch.cuda.is_available();start=time.monotonic()
    c=database();plan=load(ROOT/'vectors-plan.json');p=TRAINED/'model' if m=='ft' else pilot.CACHE.parent/'e5-base-v2'
    assert pilot.sha(p/'model.safetensors')==plan['FT' if m=='ft' else 'BASE']
    model=load_sentence_transformer(str(p),device='cuda').eval()
    sel='true' if m=='ft' else 'base=1'
    todo=[r[0] for r in c.execute("select s.k from corpus s where "+sel+" and not exists(select 1 from vectors v where v.k=s.k and v.prec=?) order by s.n,s.k",[m])]
    n=tok=0
    checkpoint_log=RUN/'logs'/('gpu-blocks-'+m+'.jsonl')
    wall_start=time.monotonic()
    with torch.inference_mode():
        for i in range(0,len(todo),128):
            if i%2048==0:
                if time.monotonic()-wall_start>6*3600 or shutil.disk_usage(RUN).free<7*1024**3:
                    raise RuntimeError('Stop at current committed GPU block: runtime or disk bound')
                try:
                    temperature=int(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],text=True,timeout=5).splitlines()[0])
                except (ValueError,OSError,subprocess.SubprocessError,IndexError):
                    temperature=None
                if temperature is not None and temperature>=84:
                    time.sleep(5)
            before_batch=time.monotonic();before_tokens=tok
            ks=todo[i:i+128];marks=','.join('?' for _ in ks)
            texts=dict(c.execute('select k,txt from corpus where k in ('+marks+')',ks));ss=[texts[k] for k in ks]
            v=model.encode(ss,batch_size=32,normalize_embeddings=True,show_progress_bar=False);assert v.shape==(len(ks),768) and np.isfinite(v).all()
            tok+=sum(model.tokenizer(ss,truncation=True,max_length=model.max_seq_length,return_length=True)['length'])
            c.executemany('insert or ignore into vectors values(?,?,?)',[(k,m,x.astype('<f4',copy=False).tobytes()) for k,x in zip(ks,v,strict=True)]);c.commit();n+=len(ks)
            with checkpoint_log.open('a',encoding='utf8') as ledger:
                ledger.write(json.dumps(dict(count=len(ks),tokens=tok-before_tokens,seconds=time.monotonic()-before_batch,first=ks[0].hex(),last=ks[-1].hex()))+'\n')
            if i%2048==0:print(m,n,time.monotonic()-start,flush=True)
    put(ROOT/f'gpu-resume-{m}.json',dict(new=n,tokens=tok,seconds=time.monotonic()-start,batch_size=32,precision='fp32',tf32=False))
if __name__=='__main__':
    if sys.argv[1]=='gpu':gpu_continue(sys.argv[2])
    else:{'costs':costs,'fit':cpu_fit}[sys.argv[1]]()

