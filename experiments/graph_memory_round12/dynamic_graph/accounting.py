import base64,statistics
from collections import defaultdict,Counter
from util12 import D,load,dump
from dictionary import encnum
from write import SEEDS
def main():
    module={};indexed=Counter();peaks=defaultdict(list);n=0
    for p in sorted((D/'events').glob('*.gz')):
        e=load(p);n=e['n'];old={};m=Counter();per=[]
        for ev in e['events']:
            curr=set(ev['words']);prior=old.get(ev['i'],set())
            changes=sorted(prior^curr);bytes_delta=sum(2+len(encnum(len(k.encode())))+len(k.encode()) for k in changes)
            per.append(dict(step=ev['step'],phase=ev['phase'],logical_changes=len(changes),delta_utf8_bytes=bytes_delta,full_event=ev['archive_bytes']))
            if ev['phase']:m.update(events=1,changes=len(changes),delta_bytes=bytes_delta,replace_archive=ev['archive_bytes'])
            old[ev['i']]=curr
        arc=(D/'archive'/(e['task']+'.bin')).stat().st_size
        m.update(all_archive=arc,archive_dir=4*n)
        module[e['task']]=dict(summary=m,steps=per);indexed.update(m)
        for step,ph,b,s,g,a,_,sp,reads,st in load(D/'states'/p.name)['rows']:
            if not ph:continue
            peaks[b,g,a].append((st['cow_index_peak'],st['whole_copy_index_peak'],st['archive_so_far']+st['offset_bytes']+st['cow_index_peak']))
        for step,ph,b,g,enc,reads,st in load(D/'exact_states'/p.name):
            if not ph:continue
            arcstep=sum(ev['archive_bytes'] for ev in e['events'][:step+1]);a='uncapped_exact' if not b else 'mutable_exact'
            peaks[b,g,a].append((st['cow'],st['cow'],st['cow']+arcstep+4*n))
    results=load(D/'results.json')['cells'];patch=load(D/'patch_results.json')['metrics'];summary={}
    for k,cell in results.items():
        ph,b,g,arm=k.split('/');b=int(b);g=int(g)
        if ph!='1':continue
        c=cell['counts'];writes=c.get('emit',0);replay=c.get('replay',0);archive=c['append'];patchbytes=patch[k]['wire']*indexed['events'];wa=indexed['delta_bytes'];mv=peaks[b,g,arm]
        can_discard=(not replay) and (arm in ['column_bloom','exact_forward','mutable_exact','uncapped_exact'])
        summary[k]=dict(component_WA=writes/wa,patch_WA=patchbytes/wa,replay_ratio=replay/wa,archive_plus_component_WA=(archive+4*indexed['events']+writes)/wa,archive_plus_patch_WA=(archive+4*indexed['events']+patchbytes)/wa,mean_bytes_per_changed_edge=writes/indexed['changes'],max_cow=max(x[0] for x in mv),actual_whole_copy_range=[min(x[1] for x in mv),max(x[1] for x in mv)],max_with_archive=max(x[2] for x in mv),no_replay_on_replacements=not replay,can_drop_archive_on_measured_replacements=can_discard)
    dump(D/'accounting.json',dict(cohorts=module,totals=indexed,summary=summary,logical_delta_encoding='per changed edge: one byte operation, one byte test position, variable unsigned UTF-8 key length, literal UTF-8 key'))
if __name__=='__main__':main()