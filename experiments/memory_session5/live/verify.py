"""Portable offline audit. Optional --execute repeats every original test in isolated child processes."""
import collections,json,sys,tempfile
from common import *
from memory import ARMS,apply_edit,packets
from grade import summary
def verify(cohort,rs,tokenize=None):
    folder=ROOT/cohort
    def get(f):return read((folder/f).relative_to(ROOT))
    for name in ('design_lock.json','prediction_lock.json'):
        for p,h in get(name).items():assert digest((folder/p).read_bytes())==h,(name,p)
    ids=get('roster.json')['ids'];saved=get('scores.json.gz')
    scores={(r['id'],r['arm']):r for r in saved};requests={}
    for f in sorted((folder/'calls').glob('*.gz')):
        rec=get('calls/'+f.name);req=rec['request'];data=rec['response'];key=f.name.split('.')[0]
        assert digest(stable(req))==key and req['seed']==17112026 and req['temperature']==0
        assert req['chat_template_kwargs']=={'enable_thinking':False} and req['cache_prompt'] is False
        assert not data['choices'][0]['message'].get('reasoning_content')
        assert data['usage']['total_tokens']==data['usage']['prompt_tokens']+data['usage']['completion_tokens']
        requests[key]=rec
    used=set();logical=collections.Counter();shared=collections.Counter();actual=collections.Counter()
    for k,r in requests.items():
        u=r['response']['usage'];actual.update({k:u[k] for k in ('prompt_tokens','completion_tokens')});actual['requests']+=1
    for i in ids:
        r=rs[i];s=src(r);slugged=slug(i);pref=get('prefix/'+slugged+'.json');prior=pref['prior_call']
        used.add(prior);pr=requests[prior];assert numbered(s) in pr['request']['messages'][1]['content']
        shared['requests']+=1;shared['tokens']+=pr['response']['usage']['total_tokens']
        assert pref['first_read_sha256']==digest(s)
        assert (folder/'work'/slugged/'solution.py').read_text(encoding='utf8')==s
        if tokenize:
            assert packets(s,pref['focus'],pref['example_run']['status'],tokenize)==pref['notes']
            assert all(tokenize(v)==pref['exposed_tokens'][a] for a,v in pref['notes'].items())
        for a in (*ARMS,'canonical','buggy'):
            scored=scores[i,a];path=folder/'artifacts'/slugged/a/'solution.py'
            if a in ARMS:
                decision=get('decisions/'+slugged+'-'+a+'.json')
                calls=decision['calls'];used.update(calls)
                assert len(calls)==1+int(decision['reread'])
                user_prompt=requests[calls[0]]['request']['messages'][1]['content']
                assert r['instruction'] in user_prompt
                assert ('Recovered working memory:\n'+(pref['notes'][a] or '(empty)')+'\n\n') in user_prompt
                last=requests[calls[-1]]
                assert decision['answer']==last['response']['choices'][0]['message']['content'].strip()
                if decision['reread']:
                    assert requests[calls[0]]['response']['choices'][0]['message']['content'].strip()=='READ'
                    assert numbered(s) in last['request']['messages'][-1]['content']
                text,act=apply_edit(s,decision['answer'])
                assert scored['action']==act and scored['reread']==decision['reread']
                assert scored['usage']=={key:sum(requests[c]['response']['usage'][key] for c in calls) for key in ('total_tokens','prompt_tokens','completion_tokens')}
                logical['calls']+=len(calls);logical['decisions']+=1
            else:text=s if a=='buggy' else r['declaration']+r['canonical_solution']
            if text is None:assert scored['patch_sha'] is None and not path.exists()
            else:
                assert digest(path.read_bytes())==scored['patch_sha']==digest(text)
                if '--execute' in sys.argv:assert run_suite(path,r['entry_point'],r['test'])==scored['evaluated'],(i,a)
            assert scored['hit']==int(scored['evaluated']['status']=='pass' and scored['action'] in ('applied','control'))
    assert used==set(requests)
    got=summary(cohort,ids,saved,rs);assert got==get('results.json')
    return {'tasks':len(ids),'actual':dict(actual),'shared_prefix':dict(shared),'logical':dict(logical),'scores':len(saved)}
def main():
    assert all(digest((ROOT/f).read_bytes())==h for f,h in read('grade_lock.json').items())
    tok=None
    if '--tokens' in sys.argv:
        from tokenizers import Tokenizer
        t=Tokenizer.from_file(str(ROOT/'tokenizer.json'));tok=lambda s:len(t.encode(s,add_special_tokens=False).ids)
    rs=corpus();res={str(s or 'primary'):verify(s,rs,tok) for s in ('','transfer')}
    assert set(read('roster.json')['ids']).isdisjoint(read('transfer/roster.json')['ids'])
    print(json.dumps({'passed':True,'cohorts':res,'reexecuted':'--execute' in sys.argv,'tokens_recounted':tok is not None},indent=1))
if __name__=='__main__':main()
