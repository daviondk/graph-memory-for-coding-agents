import gzip,json,sys,time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pipeline as base
from common import *
from policy import *
from controls import extra,CONTROLS
T=ROOT/'transfer'
def save(name,obj):(T/name).write_text(json.dumps(obj,indent=1))
def transfer_data(split,k):
    return rows((ROOT/'source'/'test' if split=='train' else T/'source')/f'{k}.jsonl.gz')
def fit():
    # Reuse exact original fitter, redirect outputs and switch training population.
    import shutil
    for n in ['PROTOCOL.md','policy.py','pipeline.py','common.py','extract5.py','qwen_tokenizer.json']:
        if n!='PROTOCOL.md':shutil.copy2(ROOT/n,T/n)
    base.ROOT=T;base.data=transfer_data;base.fit()
    save('method_lock.json',{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [ROOT/'transfer_run.py',ROOT/'controls.py',ROOT/'transfer_extract.py',T/'PROTOCOL.md',T/'fit_lock.json',T/'model.json',*sorted((T/'source').glob('*.gz'))]})
def predict(item):
    split,k=item;model=json.loads((T/'model.json').read_bytes());outfile=T/split/'sealed'/f'{k}.jsonl.gz'
    with gzip.open(outfile,'wt',encoding='utf8',compresslevel=2) as fp:
        for r in transfer_data(split,k):
            for t,states,meta in base.snapshots(r):
                if split=='train':
                    # Training dataset only selects simple controls. Learner is not selected using same-data fit results.
                    out=extra(states,meta,t,r['issue'],model)
                    rs=pages(states['rebase']);d=pages(states['drop']);cs=costs(rs)
                    for b in BUDGETS:
                        out[str(b)]['reset_tail']=greedy_base(d,order(d,meta,'tail'),costs(d),b)
                        out[str(b)]['rebased_tail']=greedy_base(rs,order(rs,meta,'tail'),cs,b)
                        out[str(b)]['rebased_center']=greedy_base(rs,order(rs,meta),cs,b)
                        out[str(b)]['latest_contiguous']=greedy_base(rs,order(rs,meta),cs,b,True)
                else:
                    out=policy(states,meta,t,r['issue'],model);others=extra(states,meta,t,r['issue'],model)
                    for b in out:out[b].update(others[b])
                fp.write(emit([r['instance'],t,out])+'\n')
    print('sealed',split,k,flush=True)
def score_for(item):
    split,k=item;folder=T/split
    base.ROOT=folder;base.data=lambda _,k:transfer_data(split,k)
    return base.score(k)
def allscores(split):
    return [r for k in range(8) for r in rows(T/split/'metrics'/f'{k}.jsonl.gz') if r['accepted']]
def best_control():
    records=allscores('train');res={}
    for b in map(str,BUDGETS):
        names=sorted(records[0]['metrics'][b]);hits={a:sum(r['metrics'][b][a][0] for r in records) for a in names}
        best=max(names,key=lambda a:hits[a]);res[b]={'name':best,'hits':hits,'n':len(records)}
    save('chosen_control.json',res)
def main():
    start=time.monotonic();fit()
    for split in ['train','test']:
        for folder in ['sealed','metrics']:(T/split/folder).mkdir(parents=True,exist_ok=True)
        with ProcessPoolExecutor(3) as ex:list(ex.map(predict,[(split,k) for k in range(8)]))
        keep=[*sorted((T/split/'sealed').glob('*.gz')),T/'method_lock.json']
        if split=='test':keep.append(T/'chosen_control.json')
        save(split+'/predictions_lock.json',{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in keep})
        with ProcessPoolExecutor(3) as ex:stats=list(ex.map(score_for,[(split,k) for k in range(8)]))
        save(split+'/coverage.json',dict(sum((Counter(s) for s in stats),Counter())))
        if split=='train':best_control()
    save('runtime.json',{'elapsed_seconds':time.monotonic()-start})
if __name__=='__main__':main()
