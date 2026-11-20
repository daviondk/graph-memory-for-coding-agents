"""Replay original tool loop for eligibility, then run two frozen interventions."""
import argparse
import json
import random
import sys
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
sys.path.insert(0,str(BASE))
import experiment as ex
from cue import Tracker,present


def write_json(p,x):
    blob=json.dumps(x,ensure_ascii=False,indent=1)
    if p.exists():
        assert json.loads(p.read_bytes())==x,p
    else:
        tmp=p.with_suffix('.tmp');tmp.write_text(blob,encoding='utf8');tmp.replace(p)


class Provider:
    def __init__(self,expected=None):
        self.expected=expected
        self.keys=[]
        self.receipts=[]

    def chat(self,messages,tools):
        messages=[{**m,'role':'user'} if i and m['role']=='system' else m for i,m in enumerate(messages)]
        data={'model':ex.MODEL,'messages':messages,'temperature':0,'seed':18112026,'max_tokens':256,'chat_template_kwargs':{'enable_thinking':False},'tools':tools,'tool_choice':'auto'}
        k=ex.sha(ex.compact(data))
        if self.expected is not None:
            assert self.expected[len(self.keys)]==k,('original replay mismatch',len(self.keys),k)
        self.keys.append(k)
        if len(self.keys)>100:
            raise ex.RequestLimit('transport_loop_cap100')
        old=BASE/'calls'/(k+'.json.gz')
        p=HERE/'calls'/(k+'.json.gz')
        if old.exists():
            source='previous-experiment'
            r=ex.read(old)
        elif p.exists():
            source='extension-cache'
            r=ex.read(p)
        else:
            assert self.expected is None,'missing original receipt'
            source='new-http'
            for attempt in range(4):
                try:
                    res=ex.requests.post('http://127.0.0.1:18961/v1/chat/completions',json=data,timeout=180)
                    if res.status_code in (200,400):
                        break
                    res.raise_for_status()
                except ex.requests.RequestException:
                    if attempt==3:
                        raise
                    time.sleep(2**attempt)
            r={'code':res.status_code,'request':data,'response':res.json()}
            ex.save(p,r)
        assert ex.sha(ex.compact(r['request']))==k
        self.receipts.append(source)
        if r['code']!=200:
            raise ex.RequestLimit('http'+str(r['code']))
        resp=r['response'];choice=resp['choices'][0];m=choice['message']
        calls=[]
        for raw in m.get('tool_calls') or []:
            fun=raw['function']
            try:
                args=json.loads(fun['arguments'])
            except (TypeError,ValueError):
                args={}
            calls.append(ex.ToolCall(raw['id'],fun['name'],args if isinstance(args,dict) else {}))
        use=resp['usage']
        return ex.LLMResponse(m.get('content') or '',calls,choice.get('finish_reason'),ex.TokenUsage(use['prompt_tokens'],use['completion_tokens'],use['total_tokens']))


def run_case(sid,arm,mode):
    target=HERE/('cpu' if arm=='replay' else 'trials')/(sid+'_'+arm+'.json.gz')
    if target.exists():
        return ex.read(target)
    cpu=arm=='replay'
    exp=ex.read(BASE/'trials'/(sid+'_baseline.json.gz'))['requests'] if cpu else None
    provider=Provider(exp)
    trackers={m:Tracker(m) for m in (['previous','returned'] if cpu else [mode])}
    def renderer(messages,**kwargs):
        out=ex.ORIGINAL(messages,**kwargs)
        for tracker in trackers.values():
            e=tracker.inspect(messages,out,kwargs['runtime'],kwargs['tool_evidence'])
            if e and not cpu:
                e['cue']=present(out,messages,e,arm)
        return out
    bundle=ex.load_pioneer_instance(sid,bench_root=ex.BENCH,cache_dir=HERE/'work'/arm,opaque_doc_ids=True,max_tool_calls_per_event=1)
    race=ex.RaceController(ex.load_race_patches(ex.BENCH/'patch_candidate_augmented.json',sid),delay_steps=0)
    race.apply_a_side_mutations(bundle.runtime)
    ex.loop.block_context_messages=renderer
    z={'id':sid,'arm':arm}
    try:
        result=ex.run_instance(bundle,provider,policy='block_context',max_events=30,race_controller=race)
        if not cpu:
            z.update(answer=result.final_answer,stop=result.stop_reason,events=result.event_count,actions=result.tool_call_count,race_events=len(result.race_events),trace=[[{'tool':c.tool_name,'arguments':c.tool_args,'observation':c.tool_result} for c in event.tool_calls] for event in result.events])
    except ex.RequestLimit as exc:
        if cpu:raise
        z.update(answer='',stop=str(exc),events=None,actions=None,race_events=None,trace=[])
    finally:
        ex.loop.block_context_messages=ex.ORIGINAL
    if cpu:
        assert provider.keys==exp
    z.update(requests=provider.keys,receipt_sources=provider.receipts,opportunities={m:t.events for m,t in trackers.items()},snapshots=next(iter(trackers.values())).snapshots)
    ex.save(target,z)
    return z


def main():
    modearg=argparse.ArgumentParser()
    modearg.add_argument('stage',choices=['cpu','run'])
    stage=modearg.parse_args().stage
    for n in ('trials','calls','cpu','work'):
        (HERE/n).mkdir(exist_ok=True)
    roster=json.loads((BASE/'input_lock_v2.json').read_bytes())['roster']
    assert len(set(roster))==40
    lock=HERE/'design_lock.json'
    hashes={f:ex.sha((HERE/f).read_bytes()) for f in ('PROTOCOL.md','cue.py','run.py')}
    if stage=='cpu':
        rows=[run_case(sid,'replay',None) for sid in roster]
        turns=sum(len(r['requests']) for r in rows)
        opportunity={m:{'cases':sum(bool(r['opportunities'][m]) for r in rows),'events':sum(len(r['opportunities'][m]) for r in rows)} for m in ('previous','returned')}
        chosen=next((m for m in ('previous','returned') if opportunity[m]['cases']>=10),None)
        summary={'matched_original_request_hashes':turns,'trajectories':len(rows),'opportunity':opportunity,'chosen':chosen,'notice_cases':sum(any(s['notice'] for s in r['snapshots']) for r in rows),'omission_cases':sum(any(s['omitted_verbatim'] for s in r['snapshots']) for r in rows)}
        write_json(HERE/'cpu_summary.json',summary)
        print(summary)
        if chosen:
            write_json(lock,{'chosen':chosen,'sha256':hashes,'baseline_lock_sha256':ex.sha((BASE/'decision_lock.json').read_bytes()),'roster':roster,'cpu_summary':summary})
        return
    design=json.loads(lock.read_bytes())
    assert hashes==design['sha256'] and roster==design['roster']
    for i,sid in enumerate(roster):
        arms=['correction','control'];random.Random('s6-highlight|'+sid).shuffle(arms)
        for arm in arms:
            run_case(sid,arm,design['chosen'])
        print(f'{i+1}/40 complete',flush=True)
    digests={p.name:ex.sha(p.read_bytes()) for p in sorted((HERE/'trials').glob('*.gz'))}
    assert len(digests)==80
    write_json(HERE/'decision_lock.json',digests)
    rows=[]
    for n,h in digests.items():
        p=HERE/'trials'/n
        assert h==ex.sha(p.read_bytes())
        r=ex.read(p);rows.append({k:r[k] for k in ('id','arm','answer')})
    write_json(HERE/'answers_for_judge.json',rows)
    print('LOCKED 80',flush=True)

if __name__=='__main__':
    main()
