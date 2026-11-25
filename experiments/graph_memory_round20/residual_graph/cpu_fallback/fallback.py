"""Small, declared training cohorts; native negative mining and native full provenance training."""
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch
import hashlib,sqlite3,sys,time
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from setup_graph import ROOT,RUN,TR,R18,TRAINED,CACHE,pilot,put,load,h
from vectors import database
from data import split,graphfiles,ProvenanceGraph,ExecutionProvenanceRankingRequest,EvidenceLabel

from forecasts import Lookup
from graph_memory.retrieval.requests import TextRankingRequest
def dirs(name):
    sub=HERE/name;sub.mkdir(exist_ok=True);private=RUN/name;private.mkdir(exist_ok=True);return sub,private
def plan():
    rows=load(ROOT/'outage-train-availability.json.gz');n=lambda v:hashlib.sha256(('r20-native-cpu-hash64|'+v['t']).encode()).digest()
    panels={'availability':sorted(r['t'] for r in rows if r['missing_ft']<=2),'hash64':sorted(r['t'] for r in sorted(rows,key=n)[:64])}
    cohorts={}
    for name,ids in panels.items():
        sub,private=dirs(name);by=set(ids)
        qs=[r for r in split('train') if r['t'] in by];cohorts[name]=dict(t=ids,requested=len(qs),q=[r['q'] for r in qs])
    put(HERE/'cohorts.json',cohorts)
    put(HERE/'protocol-lock.json',dict(files={p.name:pilot.sha(p) for p in [HERE/'PROTOCOL_RU.md',HERE/'fallback.py',HERE/'cohorts.json']},outage=pilot.sha(ROOT/'gpu-outage.json'),train_inventory=pilot.sha(ROOT/'outage-train-availability.json.gz')))
def data(stage,which=None):
    wanted=split(stage);ts=set(which) if which is not None else {r['t'] for r in wanted};qs=defaultdict(list)
    for r in wanted:
        if r['t'] in ts:qs[r['t']].append(r['q'])
    for t in sorted(ts):
        p,sha=graphfiles()[t];assert pilot.sha(p)==sha;raw=load(p);assert raw['split']==stage
        graph=ProvenanceGraph.model_validate(raw['g']);pool=pilot.native.provenance_unit_candidates(graph);text=dict(raw['q'])
        rs=[ExecutionProvenanceRankingRequest(task_id=q,query_text=text[q],candidates=tuple(pool),graph=graph) for q in qs[t]]
        labs={}
        if stage in ('train','dev'):
            source=load(TRAINED/'projection'/stage/f'{t}.json.gz')
            labs={x['q']:EvidenceLabel(task_id=x['q'],gold_answer='',gold_evidence_item_ids=tuple(x['positive']),gold_dependency_edges=()) for x in source['qs']}
        yield t,rs,labs
def cpu_encode(name):
    import torch,numpy as np
    from graph_memory.embeddings import load_sentence_transformer
    torch.set_num_threads(8);sub,private=dirs(name);c=database()
    assert load(HERE/'protocol-lock.json')['files']['cohorts.json']==pilot.sha(HERE/'cohorts.json')
    needed={'ft':{},'base':{}}
    for t,rs,_ in data('train',load(HERE/'cohorts.json')[name]['t']):
        g=rs[0].graph;K={v.item_id for v in rs[0].candidates}
        for v in g.nodes:
            s='passage: '+v.text;kh=h(s);needed['ft'][kh]=s
            if v.node_id in K:needed['base'][kh]=s
        for r in rs:
            s='query: '+r.query_text;kh=h(s);needed['ft'][kh]=needed['base'][kh]=s
    archive={};start=time.monotonic()
    for m in ['ft','base']:
        tm=time.monotonic();known={k for k, in c.execute('select k from vectors where prec=?',[m])};todo=sorted([(k,s) for k,s in needed[m].items() if k not in known],key=lambda row:(len(row[1]),row[0]))
        modelpath=TRAINED/'model' if m=='ft' else pilot.CACHE.parent/'e5-base-v2';model=load_sentence_transformer(str(modelpath),device='cpu').eval()
        tokens=0
        with torch.inference_mode():
            for pos in range(0,len(todo),32):
                batch=todo[pos:pos+32];ss=[s for _,s in batch];v=model.encode(ss,batch_size=8,normalize_embeddings=True,show_progress_bar=False)
                assert v.shape==(len(ss),768) and v.dtype==np.float32 and np.isfinite(v).all()
                tokens+=sum(model.tokenizer(ss,truncation=True,max_length=model.max_seq_length,return_length=True)['length'])
                c.executemany('insert or ignore into vectors values(?,?,?)',[(k,m,x.astype('<f4',copy=False).tobytes()) for (k,_),x in zip(batch,v,strict=True)]);c.commit()
                if pos%512==0:print(name,m,pos,len(todo),round(time.monotonic()-tm,1),flush=True)
        archive[m]=dict(needed=len(needed[m]),new=len(todo),tokens=tokens,seconds=time.monotonic()-tm)
    put(sub/'cpu-encoding.json',archive)
def ingest(stage,name):
    import torch,numpy as np
    from fit_graph import features,PrecomputedGraphFeatureProvider
    source=load(HERE/'cohorts.json')[name];chosen=source['t'] if stage=='train' else None
    facts={r['t']:r for r in load(TR/'rgcn-shapes.json.gz') if r['split']==stage}
    order=[r['q'] for r in split(stage) if chosen is None or r['t'] in set(chosen)];subset=set(order)
    total=sum((row['nodes']+1)*row['qs'] for t,row in facts.items() if chosen is None or t in set(chosen))
    sub,private=dirs(name);mmap=np.memmap(private/(stage+'.f32'),mode='w+',dtype='<f4',shape=(total,768))
    array={};qs={};labels={};c=database();lk=Lookup(c,'ft');offset=0
    for t,rs,labs in data(stage,chosen):
        provider,offset=features(rs,lk,mmap,offset);array.update(provider.tasks);qs.update({r.task_id:r for r in rs});labels.update(labs)
    assert offset==total and set(qs)==subset;mmap.flush()
    return [qs[q] for q in order],[labels[q] for q in order] if labels else [],PrecomputedGraphFeatureProvider(array,embedding_dim=768)
def train(name):
    import torch
    from fit_graph import mining,model_cfg,training,provenance_train_pair_task,build_train_pairs,DenseTaskRetriever,DenseConfig,build_model_from_config,save_rgcn_checkpoint
    from graph_memory.models.graph_retriever.provenance_training import train_provenance_graph_retriever
    torch.set_num_threads(8);sub,private=dirs(name);start=time.monotonic()
    train,labels,train_provider=ingest('train',name);dev,dev_labels,dev_provider=ingest('dev',name)
    lk=Lookup(database(),'base')
    def cached(**kw):return DenseTaskRetriever(**kw,encoder=lk)
    with patch('graph_memory.training_pairs.builder.DenseTaskRetriever',cached):
        paired=build_train_pairs([provenance_train_pair_task(r,l) for r,l in zip(train,labels,strict=True)],mining,dense_config=DenseConfig(device='cpu',model_name=str(pilot.CACHE.parent/'e5-base-v2')))
    put(sub/'train-pairs.json.gz',[p.model_dump() for p in paired.pairs])
    put(sub/'fit-lock.json',dict(protocol=pilot.sha(HERE/'protocol-lock.json'),model=model_cfg.model_dump(),trainer=training.model_dump(),pairs=pilot.sha(sub/'train-pairs.json.gz'),mine=paired.summary.model_dump(),training_queries=len(train),dev_queries=len(dev)))
    print(name,'prepared',len(train),len(dev),len(paired.pairs),'sec',time.monotonic()-start,flush=True);tm=time.monotonic()
    fit=train_provenance_graph_retriever(train_requests=train,train_labels=labels,train_pairs=paired.pairs,dev_requests=dev,dev_labels=dev_labels,model_config=model_cfg,training_config=training,text_embedding_provider=train_provider,seed_signal_provider=train_provider,dev_text_embedding_provider=dev_provider,dev_seed_signal_provider=dev_provider,device='cpu')
    m=build_model_from_config(model_cfg);m.load_state_dict(fit.best_model_state_dict);ck=sub/'best.pt'
    save_rgcn_checkpoint(ck,method_name='provenance_rgcn',model=m,epoch=fit.best_epoch,global_step=fit.global_step,best_dev_metric=fit.best_dev_metric,model_config=model_cfg,training_config=training)
    put(sub/'checkpoint.json',dict(sha=pilot.sha(ck),best_epoch=fit.best_epoch,metric=fit.best_dev_metric,steps=fit.global_step,history=list(fit.metric_records),fit_seconds=time.monotonic()-tm,preparation_seconds=tm-start))
if __name__=='__main__':
    if sys.argv[1]=='plan':plan()
    else:{'encode':cpu_encode,'train':train}[sys.argv[1]](sys.argv[2])

