"""Single-seed native hard mining, native supervised tensors, optimizer and epoch selection."""
from collections import defaultdict
from unittest.mock import patch
import gc,sys,time
from data import ROOT,RUN,TR,TRAINED,load,put,pilot,split,streams,ordered
from vectors import database
from forecasts import Lookup
from graph_memory.models.graph_retriever.provenance import provenance_train_pair_task,provenance_rgcn_model_config,tensorize_provenance_training_task,tensorize_provenance_dev_task,tensorize_provenance_ranking_task
from graph_memory.training_pairs.builder import build_train_pairs
from graph_memory.training_pairs.config import NegativeSamplingConfig
from graph_memory.training_pairs.contracts import TrainPairRecord
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever,DenseConfig
from graph_memory.models.graph_retriever.config.records import RgcnTrainingConfig
from graph_memory.models.frozen_embeddings import FrozenTaskEmbeddings,node_ids_digest
from graph_memory.models.graph_retriever.text_embeddings import PrecomputedGraphFeatureProvider
from graph_memory.models.graph_retriever.training import train_materialized_graph_retriever,RgcnDevEpochEvaluation
from graph_memory.models.graph_retriever.provenance_training import _predict_provenance_dev_from_batches
from graph_memory.evaluation.service import evaluate_results
from graph_memory.evaluation.requests import EvidenceEvaluationRequest
from graph_memory.models.graph_retriever.selection import RgcnSelectionSettings,build_selection_metrics
from graph_memory.models.graph_retriever.factory import build_model_from_config
from graph_memory.models.graph_retriever.checkpoint import save_rgcn_checkpoint
import torch,numpy as np
model_cfg=provenance_rgcn_model_config(encoder_model=str(TRAINED/'model'),encoder_dim=768,query_prefix='query: ',passage_prefix='passage: ',encoder_batch_size=64,hidden_dim=256,num_layers=3,dropout=.1)
training=RgcnTrainingConfig(optimizer_name='AdamW',learning_rate=.0001,per_device_graph_batch_size=128,max_grad_norm=1.,random_seed=13,pos_weight_enabled=True,epochs=15)
mining=NegativeSamplingConfig(random_seed=13,easy_random_per_positive=2,hard_bm25_per_positive=2,hard_dense_per_positive=1,hard_graph_neighbor_per_positive=1,hard_pool_size=30)
def pairs():
    assert (ROOT/'cost-base.json').exists()
    start=time.monotonic();lookup=Lookup(database(),'base');tasks={}
    for t,rs,labs in streams('train'):
        for r in rs:tasks[r.task_id]=provenance_train_pair_task(r,labs[r.task_id])
    def cached(**kw):return DenseTaskRetriever(**kw,encoder=lookup)
    cfg=DenseConfig(device='cpu',model_name=str(pilot.CACHE.parent/'e5-base-v2'))
    with patch('graph_memory.training_pairs.builder.DenseTaskRetriever',cached):
        got=build_train_pairs(ordered(tasks,'train'),mining,dense_config=cfg,progress_desc='train negative sampling')
    arr=[v.model_dump() for v in got.pairs]
    assert {v['task_id'] for v in arr}=={x['q'] for x in split('train')}
    put(ROOT/'train-pairs.json.gz',arr);put(ROOT/'pair-inventory.json',dict(total=len(arr),summary=got.summary.model_dump(),seconds=time.monotonic()-start,sha=pilot.sha(ROOT/'train-pairs.json.gz')))
def features(rqs,lookup,mmap,offset):
    graph=rqs[0].graph;node_ids=[n.node_id for n in graph.nodes]+['q']
    opts=dict(batch_size=64,normalize_embeddings=True,show_progress_bar=False)
    mat=lookup.encode(['passage: '+n.text for n in graph.nodes],**opts)
    qemb=lookup.encode(['query: '+r.query_text for r in rqs],**opts)
    rows={}
    for r,qv in zip(rqs,qemb,strict=True):
        view=mmap[offset:offset+len(node_ids)];view[:-1]=mat;view[-1]=qv;offset+=len(node_ids)
        rows[r.task_id]=FrozenTaskEmbeddings(task_id=r.task_id,node_ids_digest=node_ids_digest(node_ids),values=torch.from_numpy(view))
    return PrecomputedGraphFeatureProvider(rows,embedding_dim=768),offset
def materialize(stage,pair_by_id=None):
    estimates=load(TR/'rgcn-feasibility.json')['splits'][stage]
    shape=(estimates['encoder_rows_by_query'],768);path=RUN/(stage+'-features.fp32')
    mmap=np.memmap(path,dtype='<f4',shape=shape,mode='w+')
    lookup=Lookup(database(),'ft');tasks={};devrs={};labs={};offset=0
    for t,rqs,labels in streams(stage):
        provider,offset=features(rqs,lookup,mmap,offset)
        opts=dict(model_config=model_cfg,text_embedding_provider=provider,seed_signal_provider=provider)
        for r in rqs:
            q=r.task_id
            if stage=='train':v=tensorize_provenance_training_task(r,pair_by_id[q],**opts)
            elif stage=='dev':
                v=tensorize_provenance_dev_task(r,labels[q],**opts);devrs[q]=r;labs[q]=labels[q]
            else:v=tensorize_provenance_ranking_task(r,**opts)
            tasks[q]=v
    assert offset==shape[0];mmap.flush()
    return ordered(tasks,stage),devrs,labs
def fit():
    from train import pin
    pin();start=time.monotonic();rr=[TrainPairRecord.model_validate(v) for v in load(ROOT/'train-pairs.json.gz')];by=defaultdict(list)
    for row in rr:by[row.task_id].append(row)
    train,_,_=materialize('train',by)
    dev,requests,labels=materialize('dev');requests=ordered(requests,'dev');labels=ordered(labels,'dev')
    ready=time.monotonic();print('Native tensors',len(train),len(dev),'built sec',ready-start,flush=True)
    def evaluate(model,batches,device):
        rank,loss=_predict_provenance_dev_from_batches(model=model,requests=requests,batches=batches,device=device)
        got=evaluate_results(EvidenceEvaluationRequest(predictions=tuple(rank),labels=tuple(labels),graphs=()))[0]
        rec=dict(dev_recall_at_5=got.recall_at_5,dev_full_support_at_5=got.full_support_at_5,dev_full_support_at_10=got.full_support_at_10,dev_mrr=got.mrr)
        print('dev',rec,'loss',loss,flush=True)
        return RgcnDevEpochEvaluation(dev_loss=loss,selection_metrics=build_selection_metrics(**rec,dev_loss=loss),metric_records=rec)
    result=train_materialized_graph_retriever(train_tasks=train,dev_tasks=dev,train_pairs=rr,model_config=model_cfg,training_config=training,dev_evaluation_callback=evaluate,selection_settings=RgcnSelectionSettings(best_metric='dev_recall_at_5',higher_is_better=True),device='cuda',progress_desc='full native residual R-GCN')
    m=build_model_from_config(model_cfg);m.load_state_dict(result.best_model_state_dict)
    p=RUN/'best.pt';save_rgcn_checkpoint(p,method_name='provenance_rgcn',model=m,epoch=result.best_epoch,global_step=result.global_step,best_dev_metric=result.best_dev_metric,model_config=model_cfg,training_config=training)
    put(ROOT/'checkpoint.json',dict(sha=pilot.sha(p),bytes=p.stat().st_size,model=model_cfg.model_dump(),trainer=training.model_dump(),fit_seconds=time.monotonic()-ready,materialize_seconds=ready-start,
       global_steps=result.global_step,epoch=result.best_epoch,metric=result.best_dev_metric,records=list(result.metric_records)))
def lock():
    put(ROOT/'fit-lock.json',dict(files={n:pilot.sha(ROOT/n) for n in ['PROTOCOL_RU.md','protocol-lock.json','setup_graph.py','vectors.py','data.py','fit_graph.py']},
        training=training.model_dump(),model=model_cfg.model_dump(),miner=mining.model_dump(),ordering=pilot.sha(TR/'split.json.gz')))
if __name__=='__main__':
    {"pairs":pairs,"fit":fit,"lock":lock}[sys.argv[1]]()

