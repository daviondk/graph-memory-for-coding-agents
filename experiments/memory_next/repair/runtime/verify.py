"""Reconcile native solver responses with expenses from each independent experiment."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent.parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def lines(p):return [json.loads(r) for r in p.read_text(encoding='utf8').splitlines()]
def reconcile():
    native=lines(ROOT/'requests.jsonl')
    indexed={e['id']:e for e in native if e.get('http_status')==200}
    assert len(indexed)==sum(e.get('http_status')==200 for e in native)
    claimed=set();result={}
    def match(arm,rows):
        stats=Counter()
        for k,usage in rows:
            assert k in indexed and k not in claimed,(arm,k)
            e=indexed[k];claimed.add(k)
            assert e['usage']==usage
            assert e['chat_template_thinking'] is False
            stats['calls']+=1;stats['prompt_tokens']+=usage['prompt_tokens'];stats['completion_tokens']+=usage['completion_tokens']
            stats['server_seconds']+=e['seconds']
        result[arm]=dict(stats)
    for part,expected in [('repair',12),('continuation',8)]:
        folders=sorted((BASE/part/'runs').glob('*/*/complete.json'))
        assert len(folders)==expected,(part,len(folders))
        for f in folders:
            c=read(f);responses=[read(s) for s in sorted(f.parent.glob('response-*.json'))]
            assert len(responses)==c['calls'] and sum(r['usage']['prompt_tokens'] for r in responses)==c['input_tokens']
            match(part+'/'+c['id']+'/'+c['arm'],[(r['id'],r['usage']) for r in responses])
    match('time_read',[(r['response_id'],r['usage']) for r in lines(BASE/'time_read/calls.jsonl')])
    writer = lines(BASE/'repair/pipe_check/writer/model_calls.jsonl')
    assert len(writer)==40
    match('pipe_check_writer',[(r['response_id'],r['usage']) for r in writer])
    assert set(indexed)==claimed,(len(indexed),len(claimed),list(set(indexed)-claimed)[:3])
    assert len(indexed)==len(native), 'Preserve and inspect any failed native requests before sealing.'
    return {'native_calls':len(indexed),'prompt_tokens':sum(e['usage']['prompt_tokens'] for e in indexed.values()),'completion_tokens':sum(e['usage']['completion_tokens'] for e in indexed.values()),'first_call_epoch':min(e['epoch'] for e in native),'last_call_epoch':max(e['epoch'] for e in native),'by_episode_or_track':result}
if __name__=='__main__':
    summary=reconcile()
    if (ROOT/'reconciled.json').exists():assert read(ROOT/'reconciled.json')==summary
    else:(ROOT/'reconciled.json').write_text(json.dumps(summary,indent=1)+'\n',encoding='utf8')
    print('Native requests verified:',summary['native_calls'],summary['prompt_tokens'],summary['completion_tokens'])

