"""Linux offline replay against the unmodified published MemTrace runtime."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse
import gzip
import json
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'MemTrace' / 'src'))
from memtrace.contracts import (Event, EventGroup, EvidenceDraft, EvidenceKey, FactType,
                                MilestoneSpec, PlanSpec, RecallIntent, RecallTemporalScope)
from memtrace.database import StateDatabase
from memtrace.page_store import PageStore
from memtrace.planning import PlanRegistry
from memtrace.recall import RecallService
from memtrace.semantic_memory import SemanticStore


def rows(name):
    with gzip.open(HERE / name, 'rt', encoding='utf8') as f:
        yield from map(json.loads, f)


def key(path, revision):
    return EvidenceKey(FactType.CODE_OBSERVATION, 'file:' + path, 'provider_observed_read',
                       'revision:' + revision, 'main', 'CURRENT')


def ranges(spans):
    return [(lo,lo+len(lines)-1) for lo,lines in spans]


def overlap(source, low, high):
    return sum(max(0, min(end, high) - max(start, low) + 1) for start,end in source['ranges'])


def store_read(store, milestone, step, path, spans, revision):
    evidence = key(path,revision)
    sections = [{'line_range':[lo,lo+len(lines)-1], 'code':'\n'.join(lines)+'\n'} for lo,lines in spans]
    content = {'path':path, 'revision':revision, 'observed_step':step}
    if len(sections)==1:
        content.update(line_range=sections[0]['line_range'],code_excerpt=sections[0]['code'])
    else:
        content.update(code_sections=sections,line_range=[s['line_range'] for s in sections])
    ref = sha256(f'{step}/{path}'.encode()).hexdigest()[:24]
    event = Event('event-'+ref,'CODE_OBSERVED',{},(EvidenceDraft(evidence,content),),
                  (evidence.canonical_entity_id,),milestone,'read',revision,'2026-01-01T00:00:00Z')
    group = EventGroup('group-'+ref,'ACTION','run-1','main',revision,(event,),milestone,
                       created_at='2026-01-01T00:00:00Z')
    manifest = store.append_group(group) or store.checkpoint('USER_CHECKPOINT')
    assert manifest and manifest.revision_ids == (revision,)
    return dict(step=step,rev=revision,pages=[x.page_id for x in store.last_sealed],
                ranges=ranges(spans))


def retrieve(reader, milestone, repo, q, current, directory, has_any_page):
    path = q['path']
    hi = q['lo']+q['n']-1
    args = dict(repository_id=repo,run_id='run-1',branch_id='main',
                current_milestone_id=milestone,question=f"Recover the observed code from {path}, lines {q['lo']} to {hi}, before editing.",
                entity_refs=('file:'+path,))
    candidates = directory.get(path,[])
    if q['source'] is not None:
        selected = next(x for x in candidates if x['step']==q['source'])
    else:
        available = [x for x in candidates if overlap(x,q['lo'],hi)]
        selected = max(available,key=lambda x:(overlap(x,q['lo'],hi),x['step']),default=None)
    results = {}
    for mode in ('exact','direct'):
        if not has_any_page or (mode=='direct' and selected is None):
            results[mode] = dict(status='NO_HISTORY' if not has_any_page else 'NO_OVERLAP',rendered='',pages_read=0)
            continue
        if mode=='exact':
            intent = RecallIntent(recall_id=q['key']+'/exact',revision_id=current,
                                  required_evidence=(key(path,current),),**args)
        else:
            page_ids = tuple(selected['pages'])
            intent=RecallIntent(recall_id=q['key']+'/direct',revision_id=selected['rev'],
                                temporal_scope=RecallTemporalScope.HISTORICAL_EXECUTION,required_evidence=(),
                                source_memory_ref='memoryref_'+sha256('/'.join(page_ids).encode()).hexdigest()[:24],
                                direct_page_ids=page_ids,max_pages=8,max_tokens=32768,max_slice_tokens=32768,**args)
        result=reader.fault(intent)
        results[mode] = dict(status=result.block.coverage.state.value,rendered=result.block.rendered_content,
                             pages_read=len(result.trace.pages_read),page_bytes=result.trace.page_bytes_read,
                             blob_bytes=result.trace.blob_bytes_read,token_count=result.block.token_count,
                             stages=[x.value for x in result.trace.executed_stages],levels=result.trace.slice_levels,
                             source=selected['step'] if mode=='direct' else None,
                             source_revision=selected['rev'] if mode=='direct' else current)
    return results


def process(args):
    task,queries,folder=args
    token=sha256(task['id'].encode()).hexdigest()[:24]
    root=folder/token
    root.mkdir(parents=True,exist_ok=False)
    db=StateDatabase(root/'state.sqlite')
    sem=SemanticStore(db)
    registry=PlanRegistry(db,sem)
    plan=PlanSpec('Restore observed code',(MilestoneSpec('m1','Restore','Recover the requested observation',
                                                         ('Source available',),('Read it',)),))
    app=registry.initialize_task(repository_id=task['repo'],run_id='run-1',branch_id='main',revision_id='rev-0',
                                 user_request='Recover the previously observed source code',plan=plan,source_event_id='plan')
    milestone=app.current_milestone_id
    store=PageStore(root/'pages',db,'run-1','main',projector=sem.project_page)
    svc=RecallService(semantic_index=sem,page_reader=store)
    directory=defaultdict(list)
    qindex=defaultdict(list)
    for q in queries:
        qindex[q['t']].append(q)
    count=0
    seal_count=0
    start=time.perf_counter()
    predictions=[]
    for ev in task['events']:
        if ev['step']>max(qindex,default=0):
            break
        revision='rev-'+str(ev['rev'])
        for path,spans in ev['files'].items():
            entry=store_read(store,milestone,ev['step'],path,spans,revision)
            assert entry['pages']
            directory[path].append(entry)
            count+=1
            seal_count+=len(entry['pages'])
        for q in qindex.get(ev['step'],()):
            predictions.append([q['key'],retrieve(svc,milestone,task['repo'],q,revision,directory,bool(count))])
    store.close()
    db.close()
    logical_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    receipt=dict(id=task['id'],observed_groups=count,pages=seal_count,bytes_on_disk=logical_bytes,
                 seconds=time.perf_counter()-start,n=len(predictions))
    return receipt,predictions


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('destination')
    ap.add_argument('--workers',type=int,default=3)
    ap.add_argument('--synthetic',action='store_true')
    opt=ap.parse_args()
    path=HERE / opt.destination
    path.mkdir(parents=False,exist_ok=False)
    if opt.synthetic:
        task={'id':'synthetic','repo':'ex/ample','events':[{'step':1,'rev':0,'files':{'m.py':[[1,['def f():','    return 3','']]]}}]}
        qs={'synthetic':[dict(key='synthetic',t=1,path='m.py',lo=1,n=3,source=1)]}
        inputs=[task]
    else:
        qs=defaultdict(list)
        for q in rows('queries.jsonl.gz'):
            qs[q['id']].append(q)
        inputs=list(rows('stream.jsonl.gz'))
        assert len(inputs)==98
    with (ProcessPoolExecutor(max_workers=opt.workers) as pool,
          gzip.open(path/'rendered.jsonl.gz','wt',encoding='utf8') as writer,
          open(path/'cost.jsonl','w',encoding='utf8') as costs):
        jobs=[(s,qs[s['id']],path) for s in inputs if qs.get(s['id'])]
        for num,(receipt,predictions) in enumerate(pool.map(process,jobs),1):
            for pr in predictions:
                writer.write(json.dumps(pr,ensure_ascii=True,separators=(',',':'))+'\n')
            costs.write(json.dumps(receipt)+'\n')
            costs.flush()
            print(num,len(jobs),receipt,flush=True)


if __name__=='__main__':
    main()
