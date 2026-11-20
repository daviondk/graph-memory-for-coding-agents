import gzip
import json
from collections import defaultdict
from prepare import HERE,matched_inputs,r5,rows,emit


def main():
    folder=HERE/'external'
    raw=HERE.parent/'version'/'external'
    qs=defaultdict(list)
    for q in rows(folder/'queries.jsonl.gz'):
        qs[q['id'],q['t']].append(q)
    with (gzip.open(folder/'symmetric_stream.jsonl.gz','wt',encoding='utf8') as f,
          gzip.open(folder/'symmetric_oracle.jsonl.gz','wt',encoding='utf8') as oracle):
        for task,(iid,terms),original in zip(rows(raw/'source.gz'),rows(raw/'terminal.gz'),
                                            rows(folder/'stream.jsonl.gz'),strict=True):
            assert task['instance']==iid==original['id']
            events=matched_inputs(task,terms)
            assert events==original['events']
            state={'rebase':{}}
            meta=r5.anchor.newmeta()
            for info,event in zip(events,task['events'],strict=True):
                t=info['step']
                r5.anchor.anchored_advance(state,meta,event,t)
                for p,spans in info['files'].items():
                    dest=state['rebase'].setdefault(p,{})
                    for lo,ls in spans:
                        for n,s in enumerate(ls,lo):
                            dest[n]=[s,t]
                if info['changed']:
                    path=info['changed']
                    _,args,output=event
                    confirmed=r5.anchor.success(args.get('command'),path,output)
                    info['edit']={'path':path,'command':args.get('command'),'confirmed':bool(confirmed)}
                    if confirmed:
                        info['edit'].update(old_str=args.get('old_str'),new_str=args.get('new_str',''))
                    current=state['rebase'].get(path,{})
                    info['files'][path]=[[ns[0],[current[n][0] for n in ns]] for ns in r5.anchor.groups(current)]
                for q in qs.get((iid,t),()):
                    table=state['rebase'].get(q['path'],{})
                    emit(oracle,[q['key'],[table.get(n,(None,))[0] for n in range(q['lo'],q['lo']+q['n'])]])
            emit(f,{**original,'events':events})
    print('streams',sum(1 for _ in rows(folder/'symmetric_stream.jsonl.gz')),'readouts',sum(1 for _ in rows(folder/'symmetric_oracle.jsonl.gz')))


if __name__=='__main__':
    main()
