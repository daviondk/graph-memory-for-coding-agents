"""Standalone audit from stored tool projections through layout hashes, budgeted choices and edit receipts."""
import csv,gzip,hashlib,json,re,sys
from collections import Counter
from pathlib import Path
from common import *
from score import intent,matching,update_full
ROOT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
def main():
    all_counts=Counter()
    if '--tokens' in sys.argv:
        from tokenizers import Tokenizer
        tokenizer=Tokenizer.from_file(str(ROOT/'source/qwen_tokenizer.json'))
    else:tokenizer=None
    for cohort,base in [('native',ROOT),('tagged',ROOT/'tagged')]:
        manifest=load(base/'prediction_lock.json')
        for name,h in manifest['files'].items():assert digest(base/name)==h
        summary=Counter()
        for k in range(8):
            preds=iter(rows(base/'sealed'/f'{k}.jsonl.gz'))
            marks=iter(rows(base/'scores'/f'{k}.jsonl.gz'));done=None
            for srcrow in rows(base/'source'/f'{k}.jsonl.gz'):
                summary['sessions']+=1
                states={m:{} for m in ('drop','rebase','stale')};meta=newmeta();full={}
                for t,event in enumerate(srcrow['events'],1):
                    advance(states,meta,event,t);update_full(full,event)
                    if t%4 or t==len(srcrow['events']):continue
                    rr,tt,pp,ll=next(preds);assert (rr,tt)==(srcrow['row'],t)
                    summary['boundaries']+=1
                    objects={m:pages(mem) for m,mem in states.items()}
                    assert {m:hashlib.sha256(emit(pg).encode()).hexdigest() for m,pg in objects.items()}==ll
                    target=intent(srcrow['events'],t)
                    if target:
                        gold=next(marks);summary['intents']+=1;path,old,new,accepted,_,_=target;summary['accepted']+=accepted
                        assert (gold['shard'],gold['row'],gold['cut'])==(k,rr,t) and gold['accepted']==accepted
                        assert gold['old_sha']==hashlib.sha256(old.encode()).hexdigest() and gold['new_sha']==hashlib.sha256(new.encode()).hexdigest()
                        assert all(gold['ceiling'][mode]==(matching(items,range(len(items)),path,old) is not None) for mode,items in objects.items())
                        assert gold['known_whole_at_boundary']==(path in full) and gold['whole_hit']==(path in full and full[path].count(old)==1)
                    for name,(indices,cost) in pp.items():
                        arm,budget=name.split(':');budget=int(budget)
                        assert cost<=budget
                        if arm=='paths':
                            wire='\n'.join(indices);ph=target and target[0] in indices;body=None
                        else:
                            mode=arm.split('_')[0] if arm!='one_reopen' else 'rebase';items=objects[mode]
                            assert len(indices)==len(set(indices)) and all(0<=i<len(items) for i in indices)
                            wire='\n'.join(f'@@ {items[i][0]} {items[i][1]}..{items[i][2]} @@\n'+items[i][4] for i in indices)
                            ph=target and any(items[i][0]==target[0] for i in indices)
                            body=matching(items,indices,target[0],target[1]) if target else None
                        if tokenizer:assert len(tokenizer.encode(wire,add_special_tokens=False).ids)==cost
                        if target:
                            assert gold['metrics'][name]==[int(ph),int(body is not None),cost]
                            if body is not None:
                                pre=hashlib.sha256(body.encode()).hexdigest();post=hashlib.sha256(body.replace(old,new,1).encode()).hexdigest()
                                assert gold['physical'][pre]==[pre,post]
                            if gold['whole_hit']:
                                assert gold['physical'].get('whole_file')==([hashlib.sha256(full[path].encode()).hexdigest(),hashlib.sha256(full[path].replace(old,new,1).encode()).hexdigest()] if accepted else None)
                        all_counts['predictions']+=1
            assert next(preds,None) is None and next(marks,None) is None
        assert dict(summary)==load(base/'counts.json');print(cohort,dict(summary),flush=True)
        all_counts.update(summary)
    from native_audit import main as native_audit
    native_audit()
    expected=load(ROOT/'results.json')
    for cohort in ('native','tagged'):
        rs=[r for fn in sorted((ROOT if cohort=='native' else ROOT/'tagged').joinpath('scores').glob('*.gz')) for r in rows(fn)]
        assert expected[cohort]['all_intents']==len(rs)
        accepted=[r for r in rs if r['accepted']]
        assert expected[cohort]['accepted']==len(accepted)
        for b,arms in expected[cohort]['stats_accepted'].items():
            for a,values in arms.items():
                assert values=={'preimage':sum(r['metrics'][a+':'+b][1] for r in accepted),'path':sum(r['metrics'][a+':'+b][0] for r in accepted),'tokens':sum(r['metrics'][a+':'+b][2] for r in accepted)}
    print('PASS',dict(all_counts),'native tokenizer recount',bool(tokenizer))
if __name__=='__main__':main()
