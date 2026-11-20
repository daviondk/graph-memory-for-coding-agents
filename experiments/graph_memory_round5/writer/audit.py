"""Replay the unmodified incumbent byte by byte, then measure additional observation headroom."""
import base64, collections, gzip, hashlib
from schema_codec import HERE,anchor,prior,memory,rows,save
from shared import write
def full(state,p,lo,lines):
    m=state['rebase'].get(p,{})
    return int(all(m.get(lo+i,[None])[0]==s for i,s in enumerate(lines)))
def main():
    marks={(i,t):q['legacy'][0] for i,_,t,_,q in rows(HERE/'scored.jsonl.gz')}
    ct=collections.Counter(); groups=collections.Counter();ws=anchor.weights()
    with gzip.open(HERE/'headroom.jsonl.gz','wt',encoding='utf8') as out:
        for k in range(8):
            checkpoints=iter(rows(HERE/f'events_{k}.gz'))
            for task in rows(HERE/f'source_{k}.jsonl.gz'):
                iid=task['instance'];ev=task['events'];pref={'rebase':{}};meta=anchor.newmeta()
                original=memory.initial('cal_neighbor');gold={}
                for t in range(4,len(ev),4):
                    if (iid,t) not in marks:continue
                    a,obs=anchor.future_check(ev,t)
                    time_of_edit=next(j for j in range(t,min(t+4,len(ev))) if ev[j][1] is a)
                    lo,lines=anchor.invert(a,obs);gold[t]=(time_of_edit,anchor.rel(a['path']),lo,lines)
                pending={}
                for t,event in enumerate(ev):
                    if t in gold:
                        when,p,lo,lines=gold[t]; start=full(pref,p,lo,lines)
                        pending.setdefault(when,[]).append((t,start,p,lo,lines))
                    for cut,start,p,lo,lines in pending.pop(t,[]):
                        last=full(pref,p,lo,lines); limited=marks[iid,cut]
                        groups[f'{limited}|{start}|{last}']+=1
                        write(out,[iid,cut,t,p,lo,len(lines),limited,start,last])
                    anchor.anchored_advance(pref,meta,event,t+1)
                    prior.advance=anchor.anchored_advance
                    original,_=memory.transition('cal_neighbor',original,event,{'instance':iid,'issue':task['issue']},ws,4096)
                    i,j,m=next(checkpoints);assert (i,j)==(iid,t+1)
                    candidate=b'R5\x00'+original[3:]
                    assert hashlib.sha256(candidate).hexdigest()==m['legacy'][0]
                    ct['reproduced_legacy_step']+=1
                assert not pending
            assert next(checkpoints,None) is None
    save(HERE/'audit.json',dict(count=ct,limited_full_unbounded_cut_unbounded_before=groups))
    print(ct,groups)
if __name__=='__main__':main()
