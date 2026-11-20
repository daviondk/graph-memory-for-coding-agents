import os,random,sys,subprocess,time
from util import *
sys.path.insert(0,str(BASE))
import experiment as ex
class Layer:
    def __init__(self,own,prior=None):self.own=own;self.prior=prior
    def __truediv__(self,name):
        if self.prior and (self.prior/name).exists():
            q=self.prior/name
            assert digest(encode(read(q)['request']))==name.split('.')[0]
            return q
        return self.own/name
class Storage:
    def __truediv__(self,name):
        assert name in ('calls','failures')
        return Layer(ROOT/name,BASE/'calls' if name=='calls' else None)
def configure():
    for name in ('calls','failures','work','trials','judge_calls'):(ROOT/name).mkdir(exist_ok=True)
    ex.ROOT=Storage()
    rev=subprocess.check_output(['git','-C',str(ex.UP),'rev-parse','HEAD']).decode().strip()
    assert rev=='4116936349995f0f30597931c0dbbebcbf7e58ac'
    uprefs=['README.md','bench/bench_readme.md','bench/qa_agent/loop.py','bench/qa_agent/driver.py','bench/qa_agent/eval_pioneer.py','bench/qa_agent/llm_judge.py','bench/qa_agent/race.py','bench/qa_agent/prompts.py','bench/qa_agent/adapters/hotpot.py','bench/pioneer_augmented.json','bench/patch_candidate_augmented.json']
    originals=['experiment.py','grade.py','input_lock_v2.json','decision_lock.json','judge/infer.py','judge/PROTOCOL.md','judge/input_lock.json']
    lock={'upstream':rev,'upstream_input_sha256':{n:digest((ex.UP/n).read_bytes()) for n in uprefs},'sibling_sha256':{n:digest((BASE/n).read_bytes()) for n in originals},'own_sha256':{n:digest((ROOT/n).read_bytes()) for n in ('PROTOCOL.md','util.py','run.py','judge.py')},'roster':read(BASE/'input_lock_v2.json')['roster']}
    assert len(set(lock['roster']))==40
    if not (ROOT/'input_lock.json').exists():save(ROOT/'input_lock.json',dict(created=now(),inputs=lock))
    else:assert read(ROOT/'input_lock.json')['inputs']==lock
    return lock['roster']
def task(tid,arm):
    out=ROOT/'trials'/(tid+'_'+arm+'.json.gz')
    if out.exists():return
    bundle=ex.load_pioneer_instance(tid,bench_root=ex.BENCH,cache_dir=ROOT/'work'/arm,opaque_doc_ids=True,max_tool_calls_per_event=1)
    race=None
    if arm!='oracle':
        race=ex.RaceController(ex.load_race_patches(ex.BENCH/'patch_candidate_augmented.json',tid),delay_steps=0)
        race.apply_a_side_mutations(bundle.runtime)
    provider=ex.Local();z={'id':tid,'arm':arm,'policy_arg':'raw' if arm=='oracle' else arm,'race_enabled':race is not None}
    try:
        result=ex.run_instance(bundle,provider,policy=z['policy_arg'],max_events=30,race_controller=race)
        z.update(answer=result.final_answer,stop=result.stop_reason,events=result.event_count,actions=result.tool_call_count,race_events=len(result.race_events),trace=[[{'tool':c.tool_name,'arguments':c.tool_args,'observation':c.tool_result} for c in ev.tool_calls] for ev in result.events])
    except ex.RequestLimit as e:z.update(answer='',stop=str(e),events=None,actions=None,race_events=None,trace=[])
    z.update(requests=provider.requests);save(out,z)
def main():
    tids=configure()
    for j,t in enumerate(tids):
        arms=['git','system_alert','oracle'];random.Random('controls6|'+t).shuffle(arms)
        for a in arms:
            for attempt in range(4):
                try:task(t,a);break
                except ex.requests.RequestException:
                    if attempt==3:raise
                    time.sleep(2**attempt)
        print(now(),j+1,'/40 cases',len(list((ROOT/'calls').glob('*.gz'))),'new receipts',flush=True)
    decisions={p.name:digest(p.read_bytes()) for p in sorted((ROOT/'trials').glob('*.gz'))}
    assert len(decisions)==120
    save(ROOT/'decision_lock.json',{'created':now() if not (ROOT/'decision_lock.json').exists() else read(ROOT/'decision_lock.json')['created'],'trials':decisions})
if __name__=='__main__':main()

