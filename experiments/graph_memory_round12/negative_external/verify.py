from collections import Counter, defaultdict
import json, os, platform, random, statistics, subprocess
from pathlib import Path
from extract import D,get,save,h
from engine import unpack,hkey
from cost import pool
from objects import CACHE,git

def stats(group):
    return {'n':len(group),'tasks':len({r['iid'] for r in group}),'repos':len({r['repo'] for r in group}),'changed':sum(r['oracle']['new']['hit'] for r in group),'changed_tasks':len({r['iid'] for r in group if r['oracle']['new']['hit']}),'repeat_later_in_trace':sum(r['observable_later_repeat'] for r in group),'arms':{m:{'wake':sum(r['policies'][m]['trigger'] for r in group),'stale':sum(r['oracle']['new']['hit'] and not r['policies'][m]['trigger'] for r in group),'extra':sum(not r['oracle']['new']['hit'] and r['policies'][m]['trigger'] for r in group),'stdout':sum(r['policies'][m]['git_output_bytes'] for r in group)} for m in ('scope','exact','pickaxe')}}
def check():
    for lockfile in ('input.lock.json','forecast.lock.json'):
        assert all(h((D/f).read_bytes())==d for f,d in get(D/lockfile)['files'].items())
    rows=unpack('outcomes.json.gz');initial=unpack('prior_identity_audit/outcomes.json.gz');selected=get(D/'keys.json')
    def core(r):
        return (r['iid'],r['tool_call_id'],r['key'],r['support'],r['skip_reason'],[(k,v['hit']) for k,v in r['oracle'].items()],{m:s['trigger'] for m,s in r['policies'].items()})
    assert list(map(core,rows))==list(map(core,initial))
    assert [hkey(r) for r in rows]==[hkey(r) for r in selected]
    assert all(r['step']==s['step'] and r['tool_call_id']==s['tool_call_id'] for r,s in zip(rows,selected))
    assert len({hkey(r) for r in rows})==len(rows)
    bl=get(D/'blob_validation.json');assert bl['checks']==len(rows)*2 and not bl['mismatches']
    g=pool(rows);keyed={hkey(r):r for r in g};aux=[r for r in rows if r['relation']=='earlier_ancestor' and not r['skip_reason'] and r['support']!='no_prior_root_witness']
    sub={'primary':stats(g),'other_ancestor':stats(aux),'primary_rename_task':stats([r for r in g if get(D/'rename_receipt.json')[r['iid']]])}
    out={'groups':sub,'scope_kinds':dict(Counter(r['old_scope'] for r in g)),'full_key_bytes':sum(len(json.dumps(r['key'],ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()) for r in g),'old_mismatch':sum(r['skip_reason']=='old_git_has_match' for r in rows),'supports':dict(Counter(r['support'] for r in rows)),'primary_examples':[{'iid':r['iid'],'query':r['key']['literal'],'scope':r['key']['scope'],'repo':r['repo']} for r in g if r['oracle']['new']['hit']]}
    sizekeys=[r for r in g if Path(r['key']['scope']).suffix and not r['key']['globs']]
    single=unpack('timing_rows.json.gz');makes=defaultdict(list)
    for r in single:
        assert r['value']==keyed[r['id']]['oracle']['new']['hit'];makes[r['method'],r['id']].append(r['wall_ns']/1e6)
    assert all(len(v)==3 for v in makes.values()) and len(makes)==4*len(g)
    groups={'file_argument':[hkey(r) for r in sizekeys],'other':[hkey(r) for r in g if r not in sizekeys]}
    out['single_by_argument']={k:{'n':len(keys),**{m:sum(statistics.median(makes[m,n]) for n in keys) for m in ('full','scope','exact','pickaxe')}} for k,keys in groups.items()}
    out['hybrid_estimated_ms']=out['single_by_argument']['file_argument']['full']+out['single_by_argument']['other']['pickaxe']
    out['per_repo_primary']={repo:stats([r for r in g if r['repo']==repo]) for repo in sorted({r['repo'] for r in g})}
    for name in ('batch','union'):
        z=unpack(name+'_rows.json.gz');agg=get(D/(name+'_summary.json'));counts=Counter()
        for rec in z:
            expected={i for i,k in enumerate(rec['queries']) if keyed[k]['oracle']['new']['hit']}
            assert set(rec['hits'])==expected
            counts[tuple(rec['group']),rec['method']]+=1
        assert set(counts.values())=={3} and all(len({r['method'] for r in z if tuple(r['group'])==grp})==len(agg['result']) for grp,m in counts)
        out[name+'_verified_comparisons']=len(z)
        if name=='union':
            times=defaultdict(list)
            for rec in z:times[(tuple(rec['group']),rec['method'])].append(rec['wall_ns']/1e6)
            repo=defaultdict(lambda:defaultdict(float))
            for (group,m),vv in times.items():repo[group[0]][m]+=statistics.median(vv)
            totals={m:sum(v[m] for v in repo.values()) for m in agg['result']}
            out['leave_one_repo_out']={m:[min(100*(1-(totals[m]-v[m])/(totals['full']-v['full'])) for v in repo.values()),max(100*(1-(totals[m]-v[m])/(totals['full']-v['full'])) for v in repo.values())] for m in ('exact','union','exact_verify','union_verify')}
    save('results.json',out)
    current=sorted([s for s in D.iterdir() if s.is_file() and s.name not in ('verification.json','MANIFEST_SHA256.json')])
    save('verification.json',{'verified_main_cost_calls':len(single),'batch_calls_checked':out['batch_verified_comparisons'],'union_calls_checked':out['union_verified_comparisons'],'git_oracle_blobs_checked':bl['checks'],'prior_vs_corrected_invariant_records':len(initial),'interpreter':platform.python_version(),'git':subprocess.check_output(['git','--version']).decode().strip(),'files':{s.name:h(s.read_bytes()) for s in current}})
    print(out['groups']);print('single',out['single_by_argument'],out['hybrid_estimated_ms']);print('leave out',out['leave_one_repo_out'])
if __name__=='__main__':check()
