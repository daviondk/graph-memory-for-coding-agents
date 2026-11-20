"""Post-hoc fairness check: give the native selector the same public binding guard."""
from pathlib import Path
from collections import Counter
from score import j,rr,ROOT,counts,save

def main():
    observations={}
    for f in (ROOT/'runs').glob('*/*/plain.json'):
        pkg,v=f.parent.parent.name,f.parent.name
        for r in j(f): observations[pkg,v,r['key']]=r
    roster={r['key']:r for r in j(ROOT/'roster.json')}
    slices={'all':[],'both_available':[],'both_return':[],'either_missing':[]}
    plugin_failure=Counter();scope_example=[];branch_example=[]
    for rr0 in rr(ROOT/'per_check.csv'):
        r=rr0.copy()
        pkg,old,new,key=[r[x] for x in ('pkg','old','new','key')]
        o,n=observations[pkg,old,key],observations[pkg,new,key]
        for k in list(r):
            if k not in ('pkg','old','new','key'):r[k]=int(r[k])
        r['testmon_with_binding']=int(r['testmon_normal'] and o['entry']==n['entry'])
        slices['all'].append(r)
        if o['entry'] and n['entry']:slices['both_available'].append(r)
        else:slices['either_missing'].append(r)
        if o['value'][0]==n['value'][0]=='return':slices['both_return'].append(r)
        if r['changed'] and r['testmon_normal']:
            plugin_failure[(pkg,old,new,roster[key]['function'],o['value'][0],n['value'][0],o['entry']==n['entry'])]+=1
        if r['changed'] and r['scopes']:
            scope_example.append({'probe':roster[key],'old':old,'new':new,'old_value':o['value'],'new_value':n['value']})
        if r['observed_branches_guards'] and not r['scopes_guards'] and pkg not in {x['pkg'] for x in branch_example}:
            branch_example.append({'pkg':pkg,'probe':roster[key],'old':old,'new':new,'old_value':o['value'],'new_value':n['value']})
    result={'slices':{s:{m:counts(rs,m) for m in ['direct_file','scopes','scopes_guards','observed_branches_guards','testmon_normal','testmon_with_binding']} for s,rs in slices.items()},
            'testmon_stale_groups':[{ 'group':list(k),'n':v} for k,v in plugin_failure.items()],'unguarded_error_examples':scope_example,'branch_reuse_examples':branch_example}
    save(ROOT/'posthoc_baseline.json',result)
    print(result['slices']['all']['testmon_with_binding'])
if __name__=='__main__':main()
