"""Independent offline reconciliation of auxiliary HumanEval+ receipts and paired counts."""
import collections,gzip,json,os,sys
from concurrent.futures import ThreadPoolExecutor
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from common import *
from grade import paired
from memory import ARMS
def main():
    lock=read('evalplus_lock.json')
    assert all(digest((ROOT/f).read_bytes())==h for f,h in lock.items())
    ds={r['task_id'].split('/')[-1]:r for ln in gzip.decompress((ROOT/'evalplus.jsonl.gz').read_bytes()).splitlines() if (r:=json.loads(ln))}
    n=0;phys=0;timing_flips=[];replayed={}
    for c in ('','transfer'):
        folder=ROOT/c
        def get(name):return read((folder/name).relative_to(ROOT))
        original={(r['id'],r['arm']):r for r in get('scores.json.gz')}
        case={(r['id'],r['arm']):r for r in get('evalplus_rows.json.gz')}
        result=get('evalplus_results.json')
        ids=sorted(set(i for i,a in case));distinct={}
        for (i,a),v in case.items():
            r=original[i,a];n+=1
            assert v['base_hit']==r['hit'] and v['patch_sha']==r['patch_sha']
            if v['patch_sha']:
                key=i,v['patch_sha'];receipt=get('evalplus_receipts/'+slug(i)+'/'+v['patch_sha']+'.json')
                assert receipt==v['evalplus']
                path=folder/'artifacts'/slug(i)/a/'solution.py'
                assert digest(path.read_bytes())==v['patch_sha']
                distinct[key]=path
            else:assert v['evalplus']['status']=='invalid_edit'
            assert v['plus_hit']==int(v['evalplus']['status']=='pass' and r['action'] in ('applied','control'))
            assert v['first_plus']==int(v['plus_hit'] and not r['reread'])
        assert result['physical_runs']==len(distinct)
        phys+=len(distinct)
        for name,sub in [('primary',ids),('sensitivity',[i for i in ids if case[i,'canonical']['plus_hit'] and not case[i,'buggy']['plus_hit']])]:
            rr=result[name];assert rr['n']==len(sub)
            for a in (*ARMS,'buggy','canonical'):
                x=[case[i,a] for i in sub];o=rr['arms'][a]
                assert sum(r['plus_hit'] for r in x)==o['plus_solves']
                assert dict(collections.Counter(r['evalplus']['status'] for r in x))==o['status']
            for key in ('plus_hit','first_plus'):
                # order affects seed resampling; honor predeclared task order
                order=[i for i in get('roster.json')['ids'] if i in sub]
                assert rr['paired_vs_center'][key]==paired([case[i,'bundle'][key] for i in order],[case[i,'center'][key] for i in order])
        if '--execute' in sys.argv:
            import numpy
            def replay(item):
                (i,h),path=item
                et=ds[i.split('/')[-1]]
                pre='import sys\nsys.path.append('+repr(str(pathlib.Path(numpy.__file__).parent.parent))+')\n'
                suite=pre+et['test']+'\ncheck('+et['entry_point']+')\n'
                now=run_suite(path,et['entry_point'],suite)
                return (i,h),now
            results={}
            with ThreadPoolExecutor(3) as pool:
                for (i,h),now in pool.map(replay,distinct.items()):
                    expected=get('evalplus_receipts/'+slug(i)+'/'+h+'.json')
                    if now != expected:
                        assert 'timeout' in (now['status'],expected['status']), (i,h,expected,now)
                        timing_flips.append({'id':i,'hash':h,'original':expected,'repeat':now})
                    results[i,h]=now
            cohort=[]
            for i in get('roster.json')['ids']:
                def passed(a):
                    r=case[i,a];h=r['patch_sha']
                    return int(h is not None and results[i,h]['status']=='pass' and original[i,a]['action'] in ('applied','control'))
                cohort.append({k:passed(k) for k in (*ARMS,'canonical','buggy')})
            replayed[c or 'primary']={'counts':{k:sum(row[k] for row in cohort) for k in cohort[0]},'pair':paired([r['bundle'] for r in cohort],[r['center'] for r in cohort])}
            if '--save-replay' in sys.argv:
                save((folder/'evalplus_replay.json.gz').relative_to(ROOT),[{'id':i,'hash':h,'observed':o} for (i,h),o in sorted(results.items())])
    result={'verified':True,'outcomes':n,'distinct_physical_files_by_task':phys,'reexecuted':'--execute' in sys.argv,'timeout_disagreements':timing_flips,'repeat_results':replayed}
    if '--save-replay' in sys.argv:save('evalplus_timing_audit.json',result)
    print(json.dumps(result))
    if '--strict-timing' in sys.argv:assert not timing_flips,timing_flips
if __name__=='__main__':main()
