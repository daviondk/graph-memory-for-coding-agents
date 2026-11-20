"""Pre-specified sensitivity to a fixed set of otherwise unavailable, in-memory Python builtins."""
import ast
import collections
import concurrent.futures
import inspect
import re
import sys
from collections import Counter

import prepare
from independent_audit import HERE, digest, execute, get, write
import independent_sealed as sealed

EXTRA = ("bytes","bytearray","memoryview","hash","NotImplemented","BufferError","LookupError","OverflowError",
         "FloatingPointError","UnicodeError","UnicodeEncodeError","UnicodeDecodeError","UnicodeTranslateError",
         "RecursionError","MemoryError","NameError","UnboundLocalError")
INJECTION='    env={k:getattr(builtins,k) for k in allow};'
SOURCES=["worker.py","prepare.py","independent_audit.py","independent_sealed.py","independent_sensitivity.py",
         "independent_pure_worker.py","independent_pure_protocol.md"]


def expanded_worker():
    orig=(HERE/"worker.py").read_text(encoding="utf-8-sig")
    assert orig.count(INJECTION)==1
    return orig.replace(INJECTION,"    allow.update("+repr(EXTRA)+")\n"+INJECTION)


def alternate_executor():
    assert (HERE/"independent_pure_worker.py").read_text(encoding="utf8")==expanded_worker()
    src=inspect.getsource(prepare.execute)
    old='str(D/"worker.py")'
    assert src.count(old)==1
    new=src.replace(old,'str(D/"independent_pure_worker.py")')
    space=vars(prepare).copy()
    # The function source is local and verified by the manifest. No candidate text enters this transformation.
    exec(compile(new,'independent-limited-executor','exec'),space)
    return space['execute']


def sync_design():
    if (HERE/'independent_pure_lock.json').exists():
        check_design()
        return
    if any((HERE/name).exists() for name in (sealed.TEACHER,sealed.ONLINE)):
        raise RuntimeError('Sensitivity plan must be fixed before either decision lock')
    (HERE/'independent_pure_worker.py').write_text(expanded_worker(),encoding='utf8')
    run=alternate_executor()
    toy={'grade':'generated','name':'size','class':'A','source':'class A:\n    def size(self): return 0','imports':[],
         'candidate':'def size(self): return len(bytes(2))','tests':'class T(unittest.TestCase):\n    def test_n(self): self.assertEqual(2, A().size())','testclass':'T'}
    assert execute(toy)['status']=='fail' and run(toy)['status']=='pass'
    write("independent_pure_lock.json",{"files":{f:digest((HERE/f).read_bytes()) for f in SOURCES},"toys":{"bytes_primary":"fail","bytes_expanded":"pass"},"extra":EXTRA})


def check_design():
    lock=get('independent_pure_lock.json')
    assert lock['extra']==list(EXTRA)
    assert all(digest((HERE/k).read_bytes())==v for k,v in lock['files'].items())


def signature(row):
    return {k:v for k,v in row.items() if k in ('status','total','passed','skipped')}


def diagnostic(row, events):
    status=row['status'];events['statuses'][status]+=1
    if status in ('invalid','harness','process'):
        events['rejections'][status+': '+row.get('why','')]+=1
    for test,reason in row.get('failures',[]):
        tip=reason.split(':',1)[0]
        if re.match(r'^[\w.]+(?:Error|Exception)$',tip):events['errors'][tip]+=1
        m=re.search(r"NameError: name '([^']+)' is not defined",reason)
        if m:events['name_error_symbols'][m.group(1)]+=1


def tracker(mode):
    return {'statuses':Counter(),'errors':Counter(),'name_error_symbols':Counter(),'rejections':Counter()}


def grade_all():
    import types
    import copy
    seal=sealed.load_seals()
    check_design()
    expanded=alternate_executor()
    # Obtain independently validated, fixed requests and assembled classes, with the initially sealed evaluator.
    raw={r['task_id']:r for r in get('ClassEval_data.json')}
    seen={};primary={}
    original_evaluate=sealed.run_all
    def original(jobs):
        name='teacher' if isinstance(next(iter(jobs)),str) else 'online'
        seen[name]=jobs
        primary[name]=original_evaluate(jobs)
        return primary[name]
    sealed.run_all=original
    try:
        main_teacher=sealed.teacher_replay(raw);main_online=sealed.online_replay(raw)
    finally:
        sealed.run_all=original_evaluate
    allres={}
    for mode,payloads in seen.items():
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            rows=dict(zip(payloads,pool.map(expanded,payloads.values())))
        allres[mode]=rows
    details={};total_diagnostics={};outputs={}
    for mode,rows in allres.items():
        di={'original':tracker(mode),'extended':tracker(mode)};changed=[]
        for k,r in rows.items():
            p=primary[mode][k];diagnostic(p,di['original']);diagnostic(r,di['extended'])
            if signature(r)!=signature(p):changed.append({'key':k,'original':signature(p),'extended':signature(r)})
        details[mode]=changed;total_diagnostics[mode]=di
    assignments={r['id']:r['arms'] for r in get('assignment.json')}
    for source,both in (('original',primary),('extended',allres)):
        t=b=both['teacher'];o=both['online'];ts={};os={}
        for a in next(iter(assignments.values())):
            table=[t[arms[a]] for arms in assignments.values()]
            ts[a]=dict(methods=sum(x['status']=='pass' for x in table),tests=sum(x.get('passed',0) for x in table))
        for a in sealed.ARMS:
            select={k:r for k,r in o.items() if k[1]==a}
            cls={k[0] for k in select}
            os[a]=dict(classes=sum(all(r['status']=='pass' for k,r in select.items() if k[0]==c) for c in cls),
                       methods=sum(r['status']=='pass' for k,r in select.items() if k[-1]=='method'),
                       integration=sum(all(r['status']=='pass' for k,r in select.items() if k[0]==c and k[-1]=='integration') for c in cls),
                       tests=sum(r.get('passed',0) for r in select.values()))
        outputs[source]=dict(teacher=ts,online=os)
    write('independent_sensitivity.json',dict(scores=outputs,diagnostics=total_diagnostics,changed=details,decision_hashes=seal,
          jobs={mode:len(records) for mode,records in primary.items()}))
    write('independent_sealed.json',dict(decision_hashes=seal,teacher=main_teacher,online=main_online))


if __name__=='__main__':
    if sys.argv[1:]==['--freeze']:
        sync_design()
    else:
        grade_all()

