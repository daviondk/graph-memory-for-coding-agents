"""Reconstruct a shareable projection, with separate reference and production timings."""
from collections import Counter
from time import perf_counter_ns as clock
import hashlib
import sys
from common44 import D,sha,load,save

FLOW=D.parent/'flow_view'
sys.path.insert(0,str(FLOW))
import flow

def production(events,has_content):
    active={};ambiguous=set();ids={};content=set();batch=[];groups=[];pending=0
    for e in events:
        if e.event_type=='tool_call':
            idx=len(ids);assert e.call_id not in ids
            ids[e.call_id]=idx;pending+=1
            for value,(src,targets) in active.items():
                if flow._argument_contains(e,value):
                    targets.append(idx);batch.append((src,idx,1))
        elif e.event_type=='tool_output':
            idx=ids[e.call_id];pending-=1
            if has_content(e.content):content.add(idx)
            for value in {v for _,v in flow._typed_tokens(e.content)}:
                if value in ambiguous:continue
                if value not in active:
                    active[value]=(idx,[])
                elif active[value][0]!=idx:
                    src,targets=active.pop(value);ambiguous.add(value)
                    batch.extend((src,target,-1) for target in targets)
            if not pending:
                groups.append([r for r in batch if r[0] in content and r[1] in content]);batch=[]
    assert not pending and not batch
    return groups

def main():
    reg=load(D/'registration.json');assert sha(D/'PROTOCOL_RU.md')==reg['protocol']
    assert sha(FLOW/'manifest.json')==reg['flow_view']
    prior=load(FLOW/'manifest.json')['files']
    assert sha(FLOW/'flow.py')==prior['flow.py']
    pilot=flow.native.api.pilot
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    def has(text):
        return bool(pilot.token_chunks(text,tokenizer=tok,max_tokens=504,overlap_tokens=64))
    rows=[];begin=clock()
    for sh in range(8):
        p=FLOW/f'trace-{sh}.json.gz';assert sha(p)==prior[p.name]
        wanted=load(p);seen=set()
        path=flow.native.api.RAW/f'trajectories-{sh:05d}.jsonl'
        r=load(FLOW/f'shard-{sh}.json');assert sha(path)==r['source']
        for _,row in pilot.stream(path):
            name=row['session_id']
            if name not in wanted:continue
            assert name not in seen;seen.add(name)
            start=clock()
            tr=flow.native.adapt_isetrace_record(flow.native.parse_isetrace_record(row),source_revision=pilot.RAW[1])
            parsed=clock();steps=production(tr.events,has);extracted=clock()
            old,refs,_,count=flow.extract(tr.events,has)
            assert steps==old and len(refs)==len(steps)==wanted[name]['counts']['boundaries']
            frames=[];pair=Counter();live=0
            for delta,ref in zip(steps,refs):
                for a,b,s in delta:
                    pair[a,b]+=s;assert pair[a,b]>=0
                    if not pair[a,b]:del pair[a,b]
                assert pair==ref
                flags={}
                for a,b in ref:flags[a]=flags.get(a,0)|1;flags[b]=flags.get(b,0)|2
                live+=sum(v.bit_count() for v in flags.values())
                frames.append([delta,sorted(flags.items())])
            assert live==wanted[name]['counts']['live_flags']
            timing=[parsed-start,extracted-parsed,clock()-extracted]
            rows.append((hashlib.sha256(('sql-flow-v1/'+name).encode()).digest(),frames,timing))
        assert seen==set(wanted);print('shard',sh,len(seen),flush=True)
    rows.sort(key=lambda v:v[0]);assert len(rows)==len({h for h,*_ in rows})==1207
    frames=[x for _,x,_ in rows];assert sum(map(len,frames))==31279
    fixture=D/'normalized.json.gz';save(fixture,frames)
    times=D/'extraction-times.json.gz';save(times,[x for _,_,x in rows])
    save(D/'fixture-seal.json',dict(fixture=sha(fixture),times=sha(times),code=sha(D/'fixture.py'),
        registration=sha(D/'registration.json'),wall_ns=clock()-begin,
        timing_columns=['adapter','witness_extraction_including_tokenizer','independent_reference_and_projection']))
    print('sealed',sha(fixture),flush=True)

if __name__=='__main__':main()
