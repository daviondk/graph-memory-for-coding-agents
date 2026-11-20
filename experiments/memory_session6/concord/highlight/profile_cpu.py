"""Descriptive CPython renderer overhead on the stored stock trajectories, without inference."""
import json
import statistics
import time
from run import HERE,BASE,Provider,Tracker,present,ex


def main():
    cases=json.loads((HERE/'design_lock.json').read_bytes())['roster']
    rows=[]
    for sid in cases:
        exp=ex.read(BASE/'trials'/(sid+'_baseline.json.gz'))['requests']
        provider=Provider(exp);tracker=Tracker('previous')
        bundle=ex.load_pioneer_instance(sid,bench_root=ex.BENCH,cache_dir=HERE/'work'/'profile',opaque_doc_ids=True,max_tool_calls_per_event=1)
        race=ex.RaceController(ex.load_race_patches(ex.BENCH/'patch_candidate_augmented.json',sid),delay_steps=0)
        race.apply_a_side_mutations(bundle.runtime)
        def measure(messages,**kwargs):
            tick=time.perf_counter_ns()
            out=ex.ORIGINAL(messages,**kwargs)
            original_ns=time.perf_counter_ns()-tick
            tick=time.perf_counter_ns()
            e=tracker.inspect(messages,out,kwargs['runtime'],kwargs['tool_evidence'])
            if e:
                present(list(out),messages,e,'correction')
            policy_ns=time.perf_counter_ns()-tick
            rows.append(dict(id=sid,request=tracker.request,original_us=original_ns/1000,incremental_us=policy_ns/1000,event=bool(e)))
            return out
        ex.loop.block_context_messages=measure
        try:
            ex.run_instance(bundle,provider,policy='block_context',max_events=30,race_controller=race)
        finally:
            ex.loop.block_context_messages=ex.ORIGINAL
        assert exp==provider.keys
    def stats(data):
        x=sorted(data)
        return dict(n=len(x),mean_us=statistics.mean(x),median_us=statistics.median(x),p95_us=x[round(.95*(len(x)-1))])
    report={'notes':'Single CPU pass on the 197 stock prompts while the actor/judge server was in use. perf_counter covers only in-process render or additional selection/formatting, excluding transport and simulation. Not an attribution of overall model time.',
            'stock_render':stats([r['original_us'] for r in rows]),'additional_selection_and_format':stats([r['incremental_us'] for r in rows]),
            'on_event':stats([r['incremental_us'] for r in rows if r['event']]),'rows':rows}
    out=HERE/'cpu_profile.json'
    if not out.exists():out.write_text(json.dumps(report,indent=1),encoding='utf8')
    print({k:v for k,v in report.items() if k not in ('rows','notes')})

if __name__=='__main__':main()
