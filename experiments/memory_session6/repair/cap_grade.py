import copy
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import numpy
from common import *
from runner import execute
from analyze import contrast
BASE='cap1024/'
def main():
    check(read(BASE+'prediction_lock.json')['hashes']);check(read(BASE+'design_lock.json')['hashes'])
    roster=read(BASE+'roster.json');raw=read('scores.json');ext=read('plus_scores.json')
    ss={'author':copy.deepcopy(raw),'enhanced':copy.deepcopy(ext)}
    ds={r['task_id']:r for r in read('upstream-sanitized-mbpp.json')}
    enh={int(r['task_id']):r for line in gzip.decompress((ROOT/'mbppplus.jsonl.gz').read_bytes()).splitlines() if (r:=json.loads(line))}
    items={r['id']:r for r in read('roster.json')['items']}; policy=read('allocations.json')
    costs=Counter();audits=[];hits=[];deltas={};plus_inputs={}
    for k,m in roster['planned'].items():
        d=read(BASE+'calls/'+k+'.json.gz');prior=read('calls/'+k+'.json.gz')
        assert d['request']==dict(prior['request'],max_tokens=1024)
        assert d['new_key']==sha(canonical(d['request'])) and k==sha(canonical(prior['request']))
        rr=d['response'];u=rr['usage'];costs.update(unique_calls=1,prompt_tokens=u['prompt_tokens'],completion_tokens=u['completion_tokens'],native_prompt_ms=rr['timings']['prompt_ms'],native_decode_ms=rr['timings']['predicted_ms'])
        if m['role']=='audit_stop':
            audits.append({'key':k,'same_complete_text':d['same_old_text'],'uses':m['uses']});continue
        p=ROOT/(BASE+'programs/'+k+'.py'); h=sha(p.read_bytes())
        hits.append({'key':k,'same_prefix':d['same_old_prefix'],'uses':m['uses'],'new_finish':rr['choices'][0]['finish_reason'],'old_tokens':prior['response']['usage']['completion_tokens'],'new_tokens':u['completion_tokens']})
        deltas[k]=u['completion_tokens']-prior['response']['usage']['completion_tokens']
        cache={}
        for i,b in m['uses']:
            r=ds[i];entry=items[i]['interface'].split('(')[0]
            if (i,'author') not in cache:cache[i,'author']=dict(code_sha=h,**execute(p,entry,r['test_imports'],r['test_list']))
            ss['author'][str(i)][b]=cache[i,'author']
            if ext[str(i)]['covered']:
                ep=enh[i];np_site=str(pathlib.Path(numpy.__file__).resolve().parent.parent)
                setup=["import os; os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'",'import sys; sys.path.append('+repr(np_site)+')']+ep['test_imports']
                if (i,'enhanced') not in cache:cache[i,'enhanced']=dict(code_sha=h,**execute(p,entry,setup,[ep['test']]))
                ss['enhanced'][str(i)][b]=cache[i,'enhanced']
    for ep,sc in ss.items():save(BASE+ep+'_scores.json',sc)
    res={}; orig={'author':raw,'enhanced':ext}
    for ep,sc in ss.items():
        res[ep]={}
        for c,a in policy.items():
            rows=[];origrows=[];nocap=set();ct=Counter();budget=Counter();delta=Counter()
            for i,it in items.items():
                if it['cohort']!=c or not sc[str(i)].get('covered',True):continue
                fit={};ofit={};used={}
                for m,arr in a.items():
                    b=arr[str(i)];k=read(path(i,b+'.json'))['call'];fit[m]=sc[str(i)][b]['status']=='pass';ofit[m]=orig[ep][str(i)][b]['status']=='pass';used[m]=k
                    ct[m]+=int(fit[m]);budget[m]+=int(b=='current');delta[m]+=deltas.get(k,0)
                if all(roster['all_reader_requests'][used[m]]['old_finish']=='stop' for m in ('version_note','blind_note')):nocap.add(i)
                rows.append({'id':i,'changed':it['changed'],'passes':fit});origrows.append({'id':i,'changed':it['changed'],'passes':ofit})
            res[ep][c]=dict(n=len(rows),solves=ct,rereads=budget,additional_logical_output_tokens=delta,contrast=contrast(rows,'version_note','blind_note'),original_on_neither_capped=contrast(origrows,'version_note','blind_note',nocap))
    save(BASE+'results.json',dict(results=res,costs=costs,audit=audits,hits=hits))
    print(canonical(res),flush=True)
if __name__=='__main__':main()

