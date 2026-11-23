"""Single-seed, native ISETrace PU dense finetuning; no test-task inputs."""
from collections import defaultdict
import json,os,sys,time
from prepare import ROOT,RUN,pilot,load,put
from graph_memory.retrieval.requests.text import TextCandidate
from graph_memory.evaluation.requests import EvidenceLabel
from graph_memory.training_pairs.builder import build_train_pairs
from graph_memory.training_pairs.config import NegativeSamplingConfig
from graph_memory.training_pairs.requests import TrainPairBuildTask
from graph_memory.training_pairs.contracts import TrainPairRecord
from graph_memory.models.dense_finetune.data import build_dense_finetune_examples
from graph_memory.models.dense_finetune.training import DenseFinetuneRunConfig,DenseFinetuneTrainerSettings,train_dense_finetune,_TrajectoryBatchSampler
WEIGHTS=pilot.CACHE.parent/'e5-base-v2'
SET=DenseFinetuneRunConfig(variant='provenance_unit',base_model=str(WEIGHTS),trainer=DenseFinetuneTrainerSettings(device='cuda',random_seed=13,epochs=1))
def pools(which):
    trd=load(ROOT/'split.json.gz')[which];qs={};labels={};groups={}
    for t in sorted({r['t'] for r in trd}):
        row=load(RUN/'projection'/which/f'{t}.json.gz');assert row['t']==t
        pool=tuple(TextCandidate.model_validate(c) for c in row['pool'])
        for p in row['qs']:
            q=p['q'];qs[q]=pilot.TextRankingRequest(task_id=q,query_text=p['text'],candidates=pool)
            labels[q]=EvidenceLabel(task_id=q,gold_answer='',gold_evidence_item_ids=tuple(p['positive']),gold_dependency_edges=())
            groups[q]=t
    order=[r['q'] for r in trd];assert set(order)==set(qs)
    return [qs[q] for q in order],[labels[q] for q in order],groups
def pairs():
    req,lab,groups=pools('train')
    tasks=[TrainPairBuildTask(text_request=r,label=l) for r,l in zip(req,lab,strict=True)]
    cfg=NegativeSamplingConfig(random_seed=13,easy_random_per_positive=2,hard_bm25_per_positive=2,hard_dense_per_positive=0,hard_graph_neighbor_per_positive=0,hard_pool_size=30)
    start=time.monotonic();r=build_train_pairs(tasks,cfg)
    put(ROOT/'train-pairs.json.gz',[x.model_dump() for x in r.pairs])
    examples=build_dense_finetune_examples(ranking_requests=req,train_pairs=r.pairs,settings=SET.data,group_ids=groups,query_prefix=SET.query_prefix,passage_prefix=SET.passage_prefix)
    sampler=_TrajectoryBatchSampler(tuple(x.group_id for x in examples.examples),batch_size=16,seed=13)
    steps=list(sampler);pilotrows=[[examples.rows[i] for i in b] for b in steps[:6]]
    put(RUN/'bench-rows.json.gz',pilotrows)
    put(ROOT/'pair-inventory.json',dict(n_train=len(req),rows=len(examples.rows),pairs=len(r.pairs),steps=len(steps),summary=r.summary.model_dump(),pair_config=cfg.model_dump(),dense_ft=SET.model_dump(),seconds=time.monotonic()-start))
    print('pair rows,steps',len(examples.rows),len(steps),flush=True)
def pin():
    import torch
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.manual_seed(13)
def bench():
    import torch
    from graph_memory.embeddings import load_sentence_transformer
    from sentence_transformers.losses import MultipleNegativesRankingLoss
    pin();m=load_sentence_transformer(str(WEIGHTS),device='cuda').train()
    fun=MultipleNegativesRankingLoss(m);opt=torch.optim.AdamW(m.parameters(),lr=2e-5);rows=load(RUN/'bench-rows.json.gz');secs=[];los=[]
    for batch in rows:
        s=time.monotonic();keys=['anchor','positive','negative']
        fs=[{k:v.cuda() for k,v in m.tokenize([r[c] for r in batch]).items()} for c in keys]
        opt.zero_grad(set_to_none=True);loss=fun(fs,torch.empty(0,device='cuda'));loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),1.);opt.step();torch.cuda.synchronize()
        secs.append(time.monotonic()-s);los.append(float(loss.detach()))
    unit=sum(secs[1:])/len(secs[1:]);n=load(ROOT/'pair-inventory.json')['steps'];out=dict(cpu_threads=torch.get_num_threads(),fp32=True,tf32=False,gpu=torch.cuda.get_device_name(),steps=len(secs),seconds=secs,loss_smoke=los,
           eta_train_minutes=n*unit/60,full_steps=n,peak_torch_gib=torch.cuda.max_memory_allocated()/2**30,torch=torch.__version__,parents_independent=True)
    put(ROOT/'throughput.json',out);print(out,flush=True)
def run():
    import torch
    pin();t=time.monotonic();req,_,groups=pools('train');dev,lab,_=pools('dev');p=[TrainPairRecord.model_validate(x) for x in load(ROOT/'train-pairs.json.gz')]
    put(ROOT/'training-lock.json',dict(files={n:pilot.sha(ROOT/n) for n in ('PROTOCOL_RU.md','protocol-seal.json','train.py','throughput.json','train-pairs.json.gz','split.json.gz','pair-inventory.json')},train_seed=13,dev_queries=len(dev)))
    print('native training on',len(req),'dev',len(dev),flush=True)
    r=train_dense_finetune(config=SET,train_requests=req,train_pairs=p,train_group_ids=groups,dev_requests=dev,dev_labels=lab,task_local_dev=True,output_dir=RUN/'fit',model_dir=RUN/'model')
    ws={f.relative_to(RUN/'model').as_posix():pilot.sha(f) for f in sorted((RUN/'model').rglob('*')) if f.is_file()}
    put(ROOT/'trained-checkpoint.json',dict(files=ws,metric=r.selected_metric_name,value=r.selected_metric_value,metrics=list(r.metric_records),seconds=time.monotonic()-t,peak_torch_gib=torch.cuda.max_memory_allocated()/2**30))
    print('trained',r.selected_metric_name,r.selected_metric_value,flush=True)
if __name__=='__main__':{'pairs':pairs,'bench':bench,'run':run}[sys.argv[1]]()
