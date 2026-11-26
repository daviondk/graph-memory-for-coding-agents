"""CPU replay of the actual R22 winner, canonical dense orders, and R34 checkpoint cross-check."""
from pathlib import Path
import gzip,hashlib,json,os,sys,time
os.environ['CUDA_VISIBLE_DEVICES']='-1'
D=Path(__file__).resolve().parent;W=D.parents[1];R22=W/'graph_memory_round22/native_multiseed/official580'
sys.path.insert(0,str(R22))
import official as n
from graph_memory.models.graph_retriever.batching import build_evidence_dataloader
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
import numpy as np,torch
ARM='wo_chunk_adjacency'
PLAN='f806372f325b883ba87c486fabdf5575c9c618ae2c48d46b4e2312d0f4dd70a8'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def store(name,obj):
    data=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()+b'\n'
    (D/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith('.gz') else data)
def net(path,config):
    ck=load_rgcn_checkpoint(path,map_location='cpu')
    assert ck.model_config==config
    m=n.fit.build_model_from_config(config);m.load_state_dict(ck.payload['model_state_dict']);return m.eval()

def main():
    assert sha(D/'PROTOCOL_RU.md')==PLAN
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    law=load(R22/'split.json.gz')
    for part in ['train','test']:
        assert not {r['q'] for r in law['dev']} & {r['q'] for r in law[part]}
        assert not {r['t'] for r in law['dev']} & {r['t'] for r in law[part]}
    cases=load(W/'graph_memory_round34/interval_witness/dev-geometry.json')['source']['candidate_sources']
    metadata={}
    for filename,sign in cases.items():
        p=Path(filename);assert sha(p)==sign
        for z in load(p):
            metadata[z['q']]=[x['node_id'] for x in z['rr']]
    assert set(metadata)=={r['q'] for r in law['dev']}
    by={q:{k:i for i,k in enumerate(vals)} for q,vals in metadata.items()}
    for seed in map(int,sys.argv[1:] or [13,17,29,37,41]):
        final=D/f'native-{seed}.json.gz'
        if final.is_file() and (D/f'native-{seed}-seal.json').is_file():continue
        start=time.perf_counter()
        cp,weights,_=n.selection(seed);cfg=n.old.model(seed,ARM,cp)
        pub,base=n.seed_paths(seed);prefix=base/load(pub/ARM/'fit.json')['attempt'];source=prefix/'best.pt';orig=load(pub/ARM/'checkpoint.json')
        assert sha(source)==orig['sha']
        r34=W.parents[1]/f'x20-r34-dev-metric/seed-{seed}'/ARM;pick=load(r34/'dev-selection.json')
        epoch=pick['selected']['epoch'];folder=r34/pick['attempt'];actual=folder/f'ranks-{epoch}.json.gz';fc=folder/f'epoch-{epoch}.pt'
        assert sha(actual)==pick['selected']['ranks'] and sha(fc)==pick['selected']['weight']
        graph=net(source,cfg);second=n.fit.build_model_from_config(cfg);second.load_state_dict(torch.load(fc,map_location='cpu',weights_only=True));second.eval();arch=load(actual)
        ranks={};tasks={};glist=load(R22/'dev-graphs.json');con,_=n.connect(seed);lookup=n.fit.Lookup(con,'ft');ranker=n.fit.DenseTaskRetriever(encoder=lookup,device='cpu')
        size=load(R22/'input-inventory.json')['mmap_bytes']//3072;mem=np.empty((size,768),np.float32);offset=0
        for t in sorted(glist):
            p=n.DEV/(t+'.json.gz');assert sha(p)==glist[t]['graph_file']
            row=load(p);g=n.ProvenanceGraph.model_validate(row['g'])
            pool=tuple(n.pilot.native.provenance_unit_candidates(g))
            requests=[n.ExecutionProvenanceRankingRequest(task_id=q,query_text=s,candidates=pool,graph=g) for q,s in row['q']]
            provider,offset=n.fit.features(requests,lookup,mem,offset)
            for req in requests:
                q=req.task_id;rq=n.pilot.TextRankingRequest(task_id=q,query_text=req.query_text,candidates=pool)
                ids=[node.node_id for node in ranker.rank(rq)]
                assert set(ids)==set(by[q]) and len(ids)==len(by[q])
                ranks[q]={'dense':[by[q][node] for node in ids], 'full':[by[q][node] for node in arch[q]]}
                tasks[q]=n.fit.tensorize_provenance_ranking_task(req,model_config=cfg,text_embedding_provider=provider,seed_signal_provider=provider)
        con.close();assert offset==size and len(tasks)==580
        ids=[row['q'] for row in law['dev']];disagreements=0;top5=0
        with torch.inference_mode():
            for batch in build_evidence_dataloader([tasks[q] for q in ids],per_device_graph_batch_size=128,shuffle=False,random_seed=seed):
                for tag,m in [('recall',graph),('check',second)]:
                    native=n.old.orders(batch,m(batch))
                    for q,seq in native.items():
                        proj=[by[q][x] for x in seq];assert sorted(proj)==list(range(len(by[q])))
                        if tag=='check':
                            disagreements+=proj!=ranks[q]['full'];top5+=proj[:5]!=ranks[q]['full'][:5]
                        else:ranks[q][tag]=proj
        ident=sum(v['dense']!=list(range(len(v['dense']))) for v in ranks.values()) if seed==13 else None
        store(final.name,ranks)
        store(f'native-{seed}-seal.json',dict(source_weight=orig['sha'],epoch=orig['epoch'],second_weight=sha(fc),second_epoch=epoch,second_ranks=sha(actual),dense_weight=weights,code=sha(Path(__file__)),result=sha(final),count=len(ranks),candidate=sum(map(len,by.values())),
            cpu_full_order_disagree=disagreements,cpu_top5_order_disagree=top5,seed13_dense_identity_disagreements=ident,seconds=time.perf_counter()-start))
        print('Finished original dev ranks',seed,'mismatches CPU vs archived GPU under the second checkpoint',disagreements,top5,'seed13 dense identity',ident,'seconds',round(time.perf_counter()-start,1),flush=True)
        del mem,tasks,graph,second

if __name__=='__main__':main()

