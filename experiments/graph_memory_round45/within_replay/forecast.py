"""CPU-only replay of two independently selected epochs on identical native inputs."""
import os
for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','RAYON_NUM_THREADS'):os.environ[key]='2'
os.environ['CUDA_VISIBLE_DEVICES']='-1'
from collections import defaultdict
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import monotonic
D=Path(__file__).resolve().parent; W=D.parents[1]
sys.path.insert(0,str(W/'graph_memory_round41/prefix_native'))
import native
api=native.api
import numpy as np
R43=W/'graph_memory_round43/checkpoint_selection'
P=Path('D:/CodexResearch/x20-r34-dev-metric')
SEEDS=(13,17,29,37,41);ARMS=('full_rgcn','wo_chunk_adjacency')
def read(p):return native.read(p)
def save(p,x):native.save(p,x)
def sha(p):return native.sha(p)
def register():
    receipts=read(R43/'imports.json')['tensors']; dev=W/'graph_memory_round34/dev_metric'
    pairs={}
    for seed in SEEDS:
        for arm in ARMS:
            key=f'{seed}-{arm}';r=receipts[key];q=read(dev/f'dev-selection-{key}.json')
            pairs[key]={'attempt':q['attempt'],'ledger':sha(dev/f'dev-selection-{key}.json'),'dense':read(native.OFF/f'seed-{seed}/embeddings.json')['weight'],
                        'recall':r['recalled_epoch'],'budget':r['budget_epoch'],'states':{str(e['epoch']):e['weight'] for e in q['ledger'] if e['epoch'] in (r['recalled_epoch'],r['budget_epoch'])}}
    obj={'protocol':sha(D/'PROTOCOL_RU.md'),'pairs':pairs,'code':sha(Path(__file__)),'r43':sha(R43/'manifest.json'),'split':sha(native.OFF/'split.json.gz')}
    file=D/'registration.json'
    if not file.exists():save(file,obj)
    assert read(file)==obj
    return obj
def models(reg):
    result={}
    for seed in SEEDS:
        path,dense=api.signed_selection(seed)
        db,_=api.connect(seed)
        for _,alias,_ in db.execute('pragma database_list').fetchall():
            if alias!='temp' and alias.isidentifier():db.execute(f'pragma {alias}.mmap_size=1500000000')
        lookup=native.RepeatedLookup(api.fit.Lookup(db,'ft'));arms={}
        for arm in ARMS:
            choice=reg['pairs'][f'{seed}-{arm}']; assert dense==choice['dense']
            cfg=api.old.model(seed,arm,path);nets={}
            for epoch,h in choice['states'].items():
                pt=P/f'seed-{seed}'/arm/choice['attempt']/f'epoch-{epoch}.pt';assert sha(pt)==h
                net=api.fit.build_model_from_config(cfg)
                net.load_state_dict(api.torch.load(pt,weights_only=True,map_location='cpu'));nets[int(epoch)]=net.cpu().eval()
            arms[arm]=(cfg,nets)
        result[seed]=(db,lookup,arms)
    return result

def main(quick):
    start=monotonic();api.torch.set_num_threads(2);api.torch.set_num_interop_threads(1);assert not api.torch.cuda.is_available()
    reg=register();q_to_node={}
    for s in range(8):
        ids,_,_=native.indexes(s)
        q_to_node.update({q:{node:j for j,node in enumerate(nodes)} for q,nodes in ids.items()})
    assert len(q_to_node)==2000
    engines=models(reg);chunk={};q_count=0;t_count=0;global_start=monotonic();seals=[]
    def flush(i,data):
        name=f'ranks-{i}.json.gz';dest=D/name;save(dest,data);meta={'file':name,'sha':sha(dest),'registration':sha(D/'registration.json'),'questions':len(data),'traces':len(set(v[0] for v in data.values()))}
        save(D/f'ranks-{i}-seal.json',meta);seals.append(meta)
        print('sealed',i,meta['traces'],meta['questions'],round(monotonic()-global_start,1),flush=True)
    for i,(t,requests,labels) in enumerate(api.fit.streams('test')):
        assert not labels and requests
        by_q={r.task_id:[t,{}] for r in requests}
        for seed,(db,lookup,variants) in engines.items():
            cells=(len(requests[0].graph.nodes)+1)*len(requests)
            feats,used=api.fit.features(requests,lookup,np.empty((cells,768),dtype='<f4'),0);assert used==cells
            for arm,(cfg,nets) in variants.items():
                tasks=[api.fit.tensorize_provenance_ranking_task(r,model_config=cfg,text_embedding_provider=feats,seed_signal_provider=feats) for r in requests]
                for batch in api.inf.build_evidence_dataloader(tasks,per_device_graph_batch_size=128,shuffle=False,random_seed=seed):
                    assert batch.sample_node_features.device.type=='cpu'
                    for epoch,net in nets.items():
                        with api.torch.inference_mode(): vals=net(batch)
                        assert api.torch.isfinite(vals).all()
                        for q,order in api.old.orders(batch,vals).items():
                            index=q_to_node[q];assert len(index)==len(order) and set(order)==index.keys()
                            by_q[q][1][f'{seed}/{arm}/{epoch}']=[index[name] for name in order]
        assert not chunk.keys()&by_q.keys() and all(len(v[1])==15 for v in by_q.values())
        q_count+=len(by_q);t_count+=1;chunk.update(by_q)
        if quick and t_count==8:
            save(D/'pilot.json',{'traces':t_count,'questions':q_count,'forward_seconds':monotonic()-global_start,'with_setup_seconds':monotonic()-start,'cuda_visible':False,'states':15,'registration':sha(D/'registration.json')});break
        if t_count%100==0:flush(i//100,chunk);chunk={}
    if not quick:
        if chunk:flush((t_count-1)//100,chunk)
        assert t_count==1207 and q_count==2000
        save(D/'forecast-seal.json',{'shards':seals,'registration':sha(D/'registration.json'),'forward_seconds':monotonic()-global_start,'wall_seconds':monotonic()-start,'cpu_threads':2})
    for db,*_ in engines.values():db.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');args=parser.parse_args();main(args.pilot)

