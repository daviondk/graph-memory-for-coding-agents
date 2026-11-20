"""One physical archive receives the same confirmed edit information and projected current coordinates."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import gzip
import json
import sys
import native
import multiple
import hybrid
from memtrace.contracts import Event,EventGroup,EvidenceDraft,EvidenceKey,FactType,MilestoneSpec,PlanSpec
from memtrace.database import StateDatabase
from memtrace.page_store import PageStore
from memtrace.planning import PlanRegistry
from memtrace.recall import RecallService
from memtrace.semantic_memory import SemanticStore


def store_change(store,milestone,step,revision,edit):
    path=edit['path']
    evidence=EvidenceKey(FactType.CODE_CHANGE,'file:'+path,'workspace_change','revision:'+revision,'main','CURRENT')
    ref=sha256(f'change/{step}/{path}'.encode()).hexdigest()[:24]
    event=Event('event-'+ref,'CODE_CHANGED',{},(EvidenceDraft(evidence,dict(edit)),),
                ('file:'+path,),milestone,'write',revision,'2026-01-01T00:00:00Z')
    group=EventGroup('group-'+ref,'ACTION','run-1','main',revision,(event,),milestone,created_at='2026-01-01T00:00:00Z')
    manifest=store.append_group(group) or store.checkpoint('USER_CHECKPOINT')
    assert manifest
    return len(store.last_sealed)


def process(args):
    task,qs,folder=args
    path=folder/sha256(task['id'].encode()).hexdigest()[:24]
    path.mkdir(exist_ok=False)
    db=StateDatabase(path/'state.sqlite')
    sem=SemanticStore(db)
    registry=PlanRegistry(db,sem)
    plan=PlanSpec('Restore observed code',(MilestoneSpec('m1','Restore','Recover the requested observation',
                                                         ('Source available',),('Read it',)),))
    app=registry.initialize_task(repository_id=task['repo'],run_id='run-1',branch_id='main',revision_id='rev-0',
                                 user_request='Recover the previously observed source code',plan=plan,source_event_id='plan')
    milestone=app.current_milestone_id
    store=PageStore(path/'pages',db,'run-1','main',projector=sem.project_page)
    svc=RecallService(semantic_index=sem,page_reader=store)
    directory=defaultdict(list)
    qindex=defaultdict(list)
    for q in qs:qindex[q['t']].append(q)
    results=[]
    cost={'reads_recorded':0,'changes_recorded':0,'pages_written':0,'projected_rows_written':0,'resets':0}
    for ev in task['events']:
        if ev['step']>max(qindex):
            break
        rev='rev-'+str(ev['rev'])
        step=ev['step']
        if ev.get('changed'):
            path_changed=ev['changed']
            directory.pop(path_changed,None)
            cost['resets']+=1
            if ev['edit']['confirmed']:
                cost['pages_written']+=store_change(store,milestone,step,rev,ev['edit'])
                cost['changes_recorded']+=1
        for p,spans in ev['files'].items():
            if spans:
                item=native.store_read(store,milestone,step,p,spans,rev)
                cost['pages_written']+=len(item['pages'])
                cost['reads_recorded']+=1
                cost['projected_rows_written']+=sum(len(ls) for _,ls in spans)
                directory[p].append(item)
        for q in qindex.get(step,()):
            call=svc,milestone,task['repo'],q,rev,directory,bool(cost['pages_written'])
            results.append([q['key'],dict(multiple=multiple.retrieve_many(*call),hybrid=hybrid.choose(*call))])
    store.close()
    db.close()
    cost['disk_bytes']=sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
    return {'id':task['id'],**cost},results


if __name__=='__main__':
    out=native.HERE/'external'/(sys.argv[1] if len(sys.argv)>1 else 'symmetric')
    out.mkdir(exist_ok=False)
    qindex=defaultdict(list)
    for q in native.rows('external/queries.jsonl.gz'):
        qindex[q['id']].append(q)
    hybrid.HOT.update({k:v['address'] for k,v in native.rows('external/graph.jsonl.gz')})
    jobs=[(s,qindex[s['id']],out) for s in native.rows('external/symmetric_stream.jsonl.gz') if qindex[s['id']]]
    with (ProcessPoolExecutor(4) as pool,gzip.open(out/'rendered.jsonl.gz','wt',encoding='utf8') as writer,
          open(out/'cost.jsonl','w',encoding='utf8') as costs):
        for i,(receipt,data) in enumerate(pool.map(process,jobs),1):
            for row in data:writer.write(json.dumps(row,separators=(',',':'),ensure_ascii=True)+'\n')
            costs.write(json.dumps(receipt)+'\n')
            costs.flush()
            print(i,len(jobs),receipt,flush=True)
