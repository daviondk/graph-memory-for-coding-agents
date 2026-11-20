"""Audit how far the selected unchanged text lies from the replacement in its same block."""
from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import statistics
from run import HERE,BASE,Provider,Tracker,ex
from cue import changed_phrase,WORDS,HEADER


def location(base,current,e):
    before=HEADER.sub('',base,count=1)
    now=HEADER.sub('',current,count=1)
    assert changed_phrase(before,now)==(e['correction'],e['control'])
    a=[x.group().casefold() for x in WORDS.finditer(before)]
    b=list(WORDS.finditer(now));w=[x.group().casefold() for x in b]
    ops=SequenceMatcher(None,a,w,autojunk=False).get_opcodes()
    start=next(lo for op,_,_,lo,hi in ops if op in ('insert','replace') and hi>lo)
    focal_width=len(WORDS.findall(e['correction']))
    control_width=len(WORDS.findall(e['control']))
    gaps=[]
    for op,_,_,lo,hi in ops:
        if op!='equal':
            continue
        for i in range(lo,hi-control_width+1):
            fragment=now[b[i].start():b[i+control_width-1].end()]
            if fragment==e['control']:
                gaps.append((abs(i-start),i,max(0,i-(start+focal_width),start-(i+control_width))))
    assert gaps
    return min(gaps)[2]


def main():
    roster=json.loads((HERE/'design_lock.json').read_bytes())['roster']
    data=[]
    for sid in roster:
        keys=ex.read(BASE/'trials'/(sid+'_baseline.json.gz'))['requests']
        provider=Provider(keys); tracker=Tracker('previous')
        bundle=ex.load_pioneer_instance(sid,bench_root=ex.BENCH,cache_dir=HERE/'work'/'distance',opaque_doc_ids=True,max_tool_calls_per_event=1)
        race=ex.RaceController(ex.load_race_patches(ex.BENCH/'patch_candidate_augmented.json',sid),delay_steps=0)
        race.apply_a_side_mutations(bundle.runtime)
        def render(messages,**kwargs):
            out=ex.ORIGINAL(messages,**kwargs);old=tracker.previous.copy()
            e=tracker.inspect(messages,out,kwargs['runtime'],kwargs['tool_evidence'])
            if e:
                k=(e['tool_id'],e['part'])
                gap=location(old[k],tracker.previous[k],e)
                data.append(dict(id=sid,request=tracker.request,gap_tokens=gap))
            return out
        ex.loop.block_context_messages=render
        try:ex.run_instance(bundle,provider,policy='block_context',max_events=30,race_controller=race)
        finally:ex.loop.block_context_messages=ex.ORIGINAL
        assert provider.keys==keys
    vals=[x['gap_tokens'] for x in data]
    res=dict(stock_n=len(vals),median_gap_words=statistics.median(vals),max_gap_words=max(vals),within20=sum(x<=20 for x in vals),rows=data)
    p=HERE/'control_distance.json'
    if p.exists():assert json.loads(p.read_bytes())==res
    else:p.write_text(json.dumps(res,indent=1),encoding='utf8')
    print({k:v for k,v in res.items() if k!='rows'})

if __name__=='__main__':main()
