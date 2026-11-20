import argparse
import math
import re
import statistics
from common import *
from policies import allocation
def verify():
    d=read('design_lock.json');pr=read('prediction_lock.json');plus=read('plus_lock.json')
    check(d['hashes']);check(pr['hashes']);check(plus['hashes']);check(read('sources.json')['data_sha'])
    ds={r['task_id']:r for r in read('upstream-sanitized-mbpp.json')}
    old={r['task_id']:r for l in (ROOT/'upstream-mbpp.jsonl').read_bytes().splitlines() if (r:=json.loads(l))}
    items=read('roster.json')['items'];assert len(items)==96 and len({r['id'] for r in items})==96
    uses={}; starts=[]
    def request(key):
        rec=read('calls/'+key+'.json.gz');body=rec['request'];response=rec['response']
        assert key==sha(canonical(body)) and body['model']=='qwen38-27b-ud-q4km'
        assert body['temperature']==0 and body['seed']==18112026 and not body['chat_template_kwargs']['enable_thinking']
        assert len(body['messages'])==2 and body['messages'][0]['role']=='system' and body['messages'][1]['role']=='user'
        assert response['choices'][0]['message']['role']=='assistant' and response['usage']['completion_tokens']<=body['max_tokens']
        uses[key]=uses.get(key,0)+1;starts.append(rec['start'])
        return body['messages'][1]['content'],response['choices'][0]['message']['content'].strip()
    ps={}
    for r in items:
        i=r['id'];p=read(path(i,'prefix.json'));ps[i]=p
        oldtext=(ROOT/path(i,'old.txt')).read_bytes().decode();newtext=(ROOT/path(i,'current.txt')).read_bytes().decode()
        assert old[i]['text']==oldtext and ds[i]['prompt']==newtext
        assert r['old_sha']==sha(oldtext) and r['current_sha']==sha(newtext)
        assert r['changed']==(r['old_sha']!=r['current_sha'])==(oldtext!=newtext)
        ui,out=request(p['call'])
        assert ui=='Interface: '+r['interface']+'\nOriginal ticket:\n'+oldtext+'\n\nWrite a compact English requirement note of at most 28 words, preserving return conventions and edge cases if specified. Estimate from 0 (precise) to 100 (very ambiguous) how ambiguous this ticket is for implementation. Return JSON only: {"note":"...", "ambiguity":0}. Do not implement the solution.'
        assert p['note_tokens']<=40 and p['raw_tokens']<=40
        for b in ('note','raw','current'):
            q=read(path(i,b+'.json'));ticket=newtext if b=='current' else p[b]; ui,answer=request(q['call'])
            assert ui=='Required function interface: '+r['interface']+'\nTask ticket:\n'+ticket+'\n\nImplement the function in Python.'
            assert answer==q['answer'] and q['source_sha']==sha(ticket) and q['delivered_bytes']==len(ticket.encode())
            c=re.fullmatch(r'```(?:python|py)?\s*\n(.*?)\n```',answer,re.S|re.I)
            code=(c.group(1) if c else answer).strip()+'\n'
            assert q['code_sha']==sha(code) and code.encode()==(ROOT/path(i,b+'.py')).read_bytes()
    assert min(starts)>d['created'] and max(starts)<pr['created']
    assert not (set(uses) ^ {p.name.split('.')[0] for p in (ROOT/'calls').glob('*.json.gz')})
    ids=read('runtime/tokenizer_crosscheck.json.gz')['native_token_ids']
    assert all(len(ids[sha(p[k])])==p[k+'_tokens'] for p in ps.values() for k in ('note','raw'))
    scores=read('scores.json');enh=read('plus_scores.json');res=read('results.json'); maps=read('allocations.json')
    for co in ('primary','replication'):
        cr=[r for r in items if r['cohort']==co]
        assert len(cr)==(64 if co=='primary' else 32)
        a=allocation(cr,ps)
        assert {m:{str(i):b for i,b in entries.items()} for m,entries in a.items()}==maps[co]
        for endpoint,ss in [('author',scores),('enhanced',enh)]:
            rr=res[endpoint][co]
            for pol,alloc in a.items():
                sl=[r['id'] for r in cr if ss[str(r['id'])].get('covered',True)]
                n=sum(ss[str(i)][alloc[i]]['status']=='pass' for i in sl)
                assert n==rr['policy'][pol]['solve'] and len(sl)==rr['policy'][pol]['n']
                assert sum(alloc[i]=='current' for i in sl)==rr['policy'][pol]['rereads']
                assert all(ss[str(i)][alloc[i]]['code_sha']==sha((ROOT/path(i,alloc[i]+'.py')).read_bytes()) for i in sl)
    info=dict(tasks=len(items),writer_and_reader_logical_calls=sum(uses.values()),actual_calls=len(uses),unreferenced_calls=0,design_lock_sha=sha((ROOT/'design_lock.json').read_bytes()),prediction_lock_sha=sha((ROOT/'prediction_lock.json').read_bytes()),registered_before_all_native_calls=True,all_request_messages_reconstructed=True,all_generated_byte_contents_verified=True,verified_outcomes=['author','enhanced'])
    print(json.dumps(info,indent=2));return info
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',action='store_true');arg=p.parse_args();info=verify()
    if arg.record:save('verification.json',info)

