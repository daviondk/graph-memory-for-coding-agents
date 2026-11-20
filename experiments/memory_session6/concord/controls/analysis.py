from collections import Counter,defaultdict
from functools import lru_cache
import csv,itertools,math,sys,importlib.util
import numpy as np
from util import *
sys.path.insert(0,str(BASE))
import grade as original
_spec=importlib.util.spec_from_file_location('concord_missing_bounds',BASE/'judge/missing.py')
missing=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(missing)
POLICIES=['raw','system_alert','git','block_context','oracle']
DISPLAY={'raw':'Naive','system_alert':'Alert','git':'Diff','block_context':'Concord','oracle':'Oracle','correction':'Подсветка изменения','control':'Контроль подсветки'}
def judge_maps():
    p=BASE/'judge';assignment=read(p/'assignments.json.gz');v=read(p/'verdicts.json.gz')
    maps={(r['id'],'block_context' if r['arm']=='baseline' else r['arm']):(r['key'],v[r['key']]) for r in assignment if r['source']=='local'}
    a=read(ROOT/'judge_assignments.json.gz');v=read(ROOT/'verdicts.json.gz')
    maps.update({(r['id'],r['arm']):(r['key'],v[r['key']]) for r in a})
    h=BASE/'highlight_judge'
    if (h/'verdicts.json.gz').exists():
        arr=read(h/'assignments.json.gz');v=read(h/'verdicts.json.gz');maps.update({(r['id'],r['arm']):(r['key'],v[r['key']]) for r in arr})
    return maps
@lru_cache(None)
def receipt(k,source):
    paths=[BASE/'calls'/(k+'.json.gz'),source/'calls'/(k+'.json.gz')]
    p=next((p for p in paths if p.exists()),None)
    if p is None:return None
    d=read(p);assert digest(encode(d['request']))==k
    u=d['response'].get('usage') or {};t=d['response'].get('timings') or {}
    return dict(stored_in=('original' if p.parent.parent==BASE else p.parent.parent.name),sha=digest(p.read_bytes()),status=d['code'],prompt=u.get('prompt_tokens'),completion=u.get('completion_tokens'),cached=(u.get('prompt_tokens_details') or {}).get('cached_tokens'),model_ms=(t.get('prompt_ms',0)+t.get('predicted_ms',0) if t else None))
def project(with_highlight=False):
    j=judge_maps();out=[];idx={}
    q={r['id']:r for r in read(BASE/'upstream/bench/pioneer_augmented.json')['hotpotqa']}
    specs=[(ROOT,read(ROOT/'decision_lock.json')['trials']),(BASE,read(BASE/'decision_lock.json'))]
    if with_highlight:specs.append((BASE/'highlight',read(BASE/'highlight/decision_lock.json')))
    for folder,lock in specs:
        for file,sha in sorted(lock.items()):
            p=folder/'trials'/file;check(p,sha);a=read(p);arm=a['arm'];sid=a['id']
            if arm=='window':continue
            if arm=='baseline':arm='block_context'
            gold=q[sid]['answer'];em,f1=original.score(a['answer'],gold)
            calls=[receipt(k,folder) for k in a['requests']]
            receipt_ids=[]
            for k,rc in zip(a['requests'],calls):
                identity=k+'@'+(rc['sha'] if rc else 'missing')
                if identity in idx:assert idx[identity]==rc
                idx[identity]=rc;receipt_ids.append(identity)
            tools=Counter();accepted=Counter();rejected=Counter();tool_reply_bytes=Counter()
            for ev in a.get('trace',[]):
                for t in ev:
                    name=t['tool'];tools[name]+=1;tool_reply_bytes[name]+=len(str(t['observation']).encode('utf8'))
                    if str(t['observation']).startswith(('Error:','Tool error:')):rejected[name]+=1
                    else:accepted[name]+=1
            if a['actions'] is not None:assert a['actions']==sum(tools.values())
            key,grade=j.get((sid,arm),(None,None));missing=sum(z is None or z['prompt'] is None for z in calls)
            out.append(dict(id=sid,arm=arm,answer=a['answer'] or '',gold=gold,em=em,f1=f1,judge=grade,judge_key=key,
                 actions=a['actions'],events=a['events'],race=a['race_events'],stop=a['stop'],tools=tools,accepted=accepted,rejected=rejected,tool_reply_bytes=tool_reply_bytes,
                 trace_complete=a['actions'] is not None,requests=a['requests'],receipt_refs=receipt_ids,missing_usage=missing,
                 receipt_sha=sha,prompt=sum(z['prompt'] or 0 for z in calls if z),completion=sum(z['completion'] or 0 for z in calls if z),native_ms=sum(z['model_ms'] or 0 for z in calls if z)))
    return out,idx
def stats(rows):
    data=defaultdict(dict)
    for r in rows:
        assert r['id'] not in data[r['arm']]
        data[r['arm']][r['id']]=r
    ids=sorted(data['raw']); draws=np.random.default_rng(20261118).integers(0,40,(10000,40))
    armz={};pairs={};judgebounds={}
    ja=[];jv={}
    for r in rows:
        key=r['judge_key'];assert key is not None
        if key in jv:assert jv[key]==r['judge']
        jv[key]=r['judge'];ja.append(dict(id=r['id'],arm=r['arm'],key=key))
    for arm,items in data.items():
        assert sorted(items)==ids and len(ids)==40
        ix=list(items.values());s=lambda f:sum((r[f] for r in ix if r[f] is not None),0)
        t=lambda f:dict(sum((Counter(r[f]) for r in ix),Counter()))
        armz[arm]=dict(cases=40,em=s('em'),mean_f1=s('f1')/40,blinded_judge_correct=s('judge'),judge_missing=sum(r['judge'] is None for r in ix),events=s('events'),actions=s('actions'),race_events=s('race'),cases_race=sum((r['race'] or 0)>0 for r in ix),all_tool_attempts=t('tools'),tool_results_without_error_prefix=t('accepted'),explicit_tool_errors=t('rejected'),traces_missing=sum(not r['trace_complete'] for r in ix),cases_with_diff=sum(bool(r['tools'].get('diff')) for r in ix),cases_with_read=sum(bool(r['tools'].get('read_file')) for r in ix),cases_with_answer_tool=sum(bool(r['tools'].get('answer')) for r in ix),stop=dict(Counter(r['stop'] for r in ix)),logical_requests=sum(len(r['requests']) for r in ix),distinct_requests=len({k for r in ix for k in r['requests']}),prompt=s('prompt'),completion=s('completion'),native_seconds=s('native_ms')/1000,missing_usage=s('missing_usage'))
        armz[arm]['output_bytes_by_tool']=t('tool_reply_bytes')
        correct=armz[arm]['blinded_judge_correct'];unparsed=armz[arm]['judge_missing'];parsed=40-unparsed
        armz[arm].update(judge_available=parsed,judge_rate_available=(correct/parsed if parsed else None),judge_rate_bounds_all40=[correct/40,(correct+unparsed)/40])
    arms=[x for x in POLICIES+['correction','control'] if x in data]
    for i,jj in itertools.combinations(arms,2):
        a,b=data[i],data[jj];res={}
        for k in ('em','f1','judge','prompt','completion','actions','events'):
            def val(r):
                if k in ('prompt','completion') and r['missing_usage']:return np.nan
                return r[k] if r[k] is not None else np.nan
            res[k]=original.paired([val(a[s]) for s in ids],[val(b[s]) for s in ids],draws)
        res['same_requests']=sum(a[s]['requests']==b[s]['requests'] for s in ids)
        res['same_native_receipts']=sum(a[s]['receipt_refs']==b[s]['receipt_refs'] for s in ids)
        res['different_answer_with_same_requests']=sum(a[s]['answer']!=b[s]['answer'] for s in ids if a[s]['requests']==b[s]['requests'])
        assert all(a[s]['answer']==b[s]['answer'] for s in ids if a[s]['receipt_refs']==b[s]['receipt_refs'])
        key=i+' minus '+jj;pairs[key]=res
        judgebounds[key]=missing.bounds(ja,jv,i,jj)
        assert judgebounds[key]['complete_pairs']==res['judge']['paired_n']
    return dict(arms=armz,pairs=pairs,judge_bounds=judgebounds)
def physical(kind):
    p=ROOT/kind;actual=Counter()
    for f in p.glob('*.gz'):
        d=read(f);rr=d['response'];u=rr.get('usage',{});t=rr.get('timings',{})
        actual['records']+=1;actual['missing_usage']+=int(not u)
        actual['prompt']+=u.get('prompt_tokens',0);actual['completion']+=u.get('completion_tokens',0)
        actual['native_ms']+=t.get('prompt_ms',0)+t.get('predicted_ms',0)
    return dict(actual)
def main(with_highlight=False):
    suffix='_with_highlight' if with_highlight else '';rows,idx=project(with_highlight)
    if with_highlight:assert len(rows)==280
    else:assert len(rows)==200
    res=stats(rows);res['physical_actor_new']=physical('calls');res['physical_judge_new']=physical('judge_calls')
    extra=[r for r in rows if r['arm'] in ('git','system_alert','oracle')]
    own={p.name.split('.')[0] for p in (ROOT/'calls').glob('*.gz')}
    used={k for r in extra for k in r['requests']};prev={k for k in used if (BASE/'calls'/(k+'.json.gz')).exists()}
    res['actor_extra_audit']=dict(logical_requests=sum(len(r['requests']) for r in extra),distinct_keys=len(used),keys_reused_from_original=len(prev),distinct_own_used=len(used&own),unused_own_receipts=sorted(own-used),missing_keys=sorted(used-prev-own))
    original_recovery=[p.name for p in (ROOT/'recovery_default_encoding/trials').glob('*.gz')]
    res['encoding_recovery']=dict(completed_before_restart=len(original_recovery),identical_full_trials_after_restart=sum(read(ROOT/'trials'/n)==read(ROOT/'recovery_default_encoding/trials'/n) for n in original_recovery))
    save(ROOT/('cases'+suffix+'.json.gz'),rows);save(ROOT/('native_index'+suffix+'.json.gz'),idx);save(ROOT/('results'+suffix+'.json'),res)
    with (ROOT/('paired'+suffix+'.csv')).open('w',newline='',encoding='utf8') as fh:
        w=csv.writer(fh);w.writerow(['first_minus_second','endpoint','paired_n','delta','95_low','95_high','wins','losses','ties','p_exact'])
        for pair,z in res['pairs'].items():
            for ep,v in z.items():
                if isinstance(v,dict) and v.get('paired_n'):w.writerow([pair,ep,v['paired_n'],v['delta'],*v['ci'],v['wins'],v['losses'],v['ties'],v['exact_sign_p']])
    with (ROOT/('partial_identification'+suffix+'.csv')).open('w',newline='',encoding='utf8') as fh:
        w=csv.writer(fh);w.writerow(['first_minus_second','all_n','known_pairs','known_pair_delta','tied_missing_same_prompt','min_delta_all','max_delta_all'])
        for pair,z in res['judge_bounds'].items():w.writerow([pair,z['n'],z['complete_pairs'],z['complete_pair_delta'],z['shared_unknown_ties'],*z['identified_delta_interval']])
if __name__=='__main__':main('--highlight' in sys.argv)

