"""Additional past-only comparators. No outcome fields are accessible in the input."""
from collections import defaultdict
import gzip
import json
import time
import sys
from predict import ROOT, author, dumps, features, TYPES, sha_bytes
from token_predict import token_count, fit
from e3_predict import recent_extras, add
from score import readgz

def e2():
    for r in readgz('histories.jsonl.gz'):
        h=r['H'][:3*len(r['H'])//4]
        raw,official,_,orders=features(h)
        candidates=set(orders['frequency'])
        pref=1; seen_calls=[]
        for msg in h:
            size=len(json.dumps(msg,ensure_ascii=False))
            # A partially visible message is excluded, so all arguments here were available.
            if pref+size>len(raw):break
            pref+=size+2
            if msg.get('role')!='assistant':continue
            for call in msg.get('tool_calls') or []:
                arg=call.get('function',{}).get('arguments') if isinstance(call,dict) else None
                if not arg:continue
                vals=author.atoms_in_text(arg if isinstance(arg,str) else json.dumps(arg,ensure_ascii=False))
                seen_calls.append({(k,v) for k,vs in vals.items() for v in vs} & candidates)
        repo=orders['author_grouped']
        for name,n in [('all_calls',len(seen_calls)),('one_call',1),('recent_messages',0)]:
            if n==0:
                order=orders['recent'] if name=='recent_messages' else orders['frequency']
            else:
                order=[];placed=set()
                for vals in reversed(seen_calls[-n:]):
                    order.extend(a for a in repo if a in vals and a not in placed)
                    placed.update(vals)
                order.extend(a for a in orders['frequency'] if a not in placed)
            cap=token_count(official)
            items,s=fit(order,cap,token_count,True)
            yield {'i':r['i'],'arm':name,'S':s,'items':items,'cap':cap,'used':token_count(s)}

def e3():
    prev=defaultdict(list)
    for r in readgz('e3_prefixes.jsonl.gz'):
        i,j,s=r['i'],r['j'],r['S']
        cap=token_count(s)
        earlier=prev[i]
        assert len(earlier)==j
        if j:
            prior=recent_extras(earlier,s)
            all_types=[[a for a in sorted(prior) if a[0]==k] for k in TYPES]
            oldest_agnostic=[ls[ind] for ind in range(max((len(ls) for ls in all_types),default=0)) for ls in all_types if ind<len(ls)]
            args={'last_summary':recent_extras(earlier[-1:],s),'type_order':[a for ls in all_types for a in ls],'unordered_round_robin':oldest_agnostic}
            for arm,cands in args.items():
                _,extra=fit(cands,cap//10,token_count,True)
                out=add(s,extra,cap)
                yield {'i':i,'j':j,'arm':arm,'S':out,'cap':cap,'used':token_count(out)}
        earlier.append(s)

def main(task):
    start=time.perf_counter();num=0
    pred=f'robust_{task}.jsonl.gz'
    with gzip.open(ROOT/pred,'wt',encoding='utf8') as f:
        for r in {'e2':e2,'e3':e3}[task]():
            assert r['used']<=r['cap']
            f.write(dumps(r)+'\n');num+=1
    names=[pred,'robust_predict.py','ROBUSTNESS.md','histories.jsonl.gz' if task=='e2' else 'e3_prefixes.jsonl.gz']
    (ROOT/f'robust_{task}_lock.json').write_text(json.dumps({'sha256':{n:sha_bytes((ROOT/n).read_bytes()) for n in names},'n':num,'wall_s':time.perf_counter()-start},indent=1))
if __name__=='__main__':main(sys.argv[1])

