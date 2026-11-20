"""Re-execute all three upstream decision loops against signed original native responses, network disabled."""
import random,sys,tempfile
from util import *
sys.path.insert(0,str(BASE))
import experiment as ex
class CacheOnly:
    def __init__(self,keys):self.keys=keys;self.pos=0
    def __truediv__(self,name):
        assert name=='calls'
        return self
    def locate(self,filename):
        k=filename.split('.')[0];assert self.keys[self.pos]==k;self.pos+=1
        if self.pos>100:return ROOT/'calls'/filename
        candidates=[BASE/'calls'/filename,ROOT/'calls'/filename]
        p=next(p for p in candidates if p.exists());assert digest(encode(read(p)['request']))==k
        return p
class Nested:
    def __init__(self,c):self.c=c
    def __truediv__(self,filename):return self.c.locate(filename)
class Backend:
    def __init__(self,c):self.c=c
    def __truediv__(self,name):assert name=='calls';return Nested(self.c)
def replay():
    lock=read(ROOT/'decision_lock.json')['trials'];assert len(lock)==120
    ex.requests.post=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('offline replay attempted a network call'))
    initialization={};stub_checked=False
    with tempfile.TemporaryDirectory(prefix='concord5-replay-') as tmp:
        for fn,h in sorted(lock.items()):
            p=ROOT/'trials'/fn;check(p,h);r=read(p);t=r['id'];arm=r['arm']
            cache=CacheOnly(r['requests']);ex.ROOT=Backend(cache)
            a=ex.load_pioneer_instance(t,bench_root=ex.BENCH,cache_dir=pathlib.Path(tmp)/arm,opaque_doc_ids=True,max_tool_calls_per_event=1)
            def docs():
                dr=pathlib.Path(tmp)/arm/'hotpotqa'/t/'corpus/original'
                return {f.name:digest(f.read_bytes()) for f in sorted(dr.glob('*.json'))}
            before=docs();assert before
            zz=initialization.setdefault(t,{'pristine_sha256':digest(encode(before)),'initial_docs':len(before),'arms':{}})
            assert zz['pristine_sha256']==digest(encode(before))
            if not stub_checked:
                sampler=ex.Local()
                try:ex.run_instance(a,sampler,policy='reread',max_events=30)
                except NotImplementedError as e:
                    assert 'not implemented' in str(e) and not sampler.requests;stub_checked=True
                else:raise AssertionError('unexpected reread implementation')
            race=None
            if arm!='oracle':
                race=ex.RaceController(ex.load_race_patches(ex.BENCH/'patch_candidate_augmented.json',t),delay_steps=0);race.apply_a_side_mutations(a.runtime)
            after=docs();assert set(after)==set(before)
            zz['arms'][arm]={'after_init_sha256':digest(encode(after)),'docs_edited_before_first_request':sum(after[n]!=before[n] for n in after)}
            if arm=='oracle':assert before==after
            provider=ex.Local()
            try:
                y=ex.run_instance(a,provider,policy=r['policy_arg'],max_events=30,race_controller=race)
                trace=[[dict(tool=c.tool_name,arguments=c.tool_args,observation=c.tool_result) for c in ev.tool_calls] for ev in y.events]
                assert [y.final_answer,y.stop_reason,y.event_count,y.tool_call_count,len(y.race_events),trace]==[r['answer'],r['stop'],r['events'],r['actions'],r['race_events'],r['trace']]
            except ex.RequestLimit as err:assert str(err)==r['stop']
            assert provider.requests==r['requests']
    assert all(z['arms']['git']==z['arms']['system_alert'] for z in initialization.values())
    save(ROOT/'workspace_audit.json.gz',initialization)
    save(ROOT/'offline_actor_verified.json',dict(regenerated_trajectories=len(lock),network_calls=0,all_traces_and_exact_message_hashes_match=True,reread_placeholder_tested_without_any_LLM_call=stub_checked))
if __name__=='__main__':replay()

