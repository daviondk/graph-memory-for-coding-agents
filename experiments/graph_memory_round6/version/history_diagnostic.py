"""Exploratory after primary: separate addressable historic evidence from a capacity miss."""
import collections
import gzip
import json
from replay import HERE, old, inputs, jobs, save, check
from version_policy import next_root


def main():
    check('evaluation_lock.json')
    outcomes={(r['panel'],r['id'],r['cut']):r for r in old.rr(HERE/'block_outcomes.jsonl.gz')}
    summary=collections.defaultdict(collections.Counter)
    with gzip.open(HERE/'history_records.jsonl.gz','wt',encoding='utf8') as out:
        for panel,k in jobs():
            src,pair=inputs(panel,k);raw=dict(old.rr(pair))
            for task in old.rr(src):
                iid=task['instance'];events=task['events']
                state={'rebase':{}};meta=old.anchor.newmeta();root=True
                ever=collections.defaultdict(set)
                literal=collections.defaultdict(set)
                for step,(event,extra) in enumerate(zip(events,raw[iid],strict=True),1):
                    _,args,obs=event
                    path=old.anchor.rel(args.get('path'))
                    if path:
                        literal[path].update(old.anchor.printed(obs).values())
                        for field in ('old_str','new_str'):
                            if isinstance(args.get(field),str):
                                # Grant boundary fragments even when they might denote sub-line edits.
                                literal[path].update(args[field].split('\n'))
                    old.anchor.anchored_advance(state,meta,event,step)
                    for p,n,s,_ in old.pol.readlines(extra,root):
                        state['rebase'].setdefault(p,{})[n]=[s,step]
                        literal[p].add(s)
                    root=next_root(root,extra)
                    for p,m in state['rebase'].items():
                        ever[p].update(v[0] for v in m.values())
                    r=outcomes.get((panel,iid,step))
                    if not r:continue
                    args,obs=old.anchor.future_check(events,step)
                    lo,ls=old.anchor.invert(args,obs)
                    p=r['path'];table=state['rebase'].get(p,{})
                    free=all(table.get(lo+j,[None])[0]==s for j,s in enumerate(ls))
                    any_now=set(ls).issubset(v[0] for v in table.values())
                    any_history=all(s in ever[p] or s in literal[p] for s in ls)
                    bucket='bounded_hit' if r['out']['r5']['full'] else 'unbounded_address_hit' if free else 'all_in_current_unbounded_text' if any_now else 'all_in_history_or_arguments' if any_history else 'incomplete_attributed_history'
                    summary[panel][bucket]+=1
                    summary[panel]['unbounded_exact_total']+=int(free)
                    old.write(out,[panel,iid,step,bucket,free,any_now,any_history,len(ls),sum(s not in ever[p] and s not in literal[p] for s in ls)])
    save('history_diagnostic.json',summary)
    print(json.dumps(summary))


if __name__=='__main__':main()
