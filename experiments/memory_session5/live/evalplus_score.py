"""Secondary endpoint on unmodified public EvalPlus OriginFmt tests."""
import collections,concurrent.futures,gzip,json,subprocess,time
from common import *
from memory import ARMS
from grade import paired
def main():
    import numpy
    check=read('evalplus_source.json');assert digest((ROOT/'evalplus.jsonl.gz').read_bytes())==check['sha256']
    rs=corpus();ep={r['task_id'].split('/')[-1]:r for ln in gzip.decompress((ROOT/'evalplus.jsonl.gz').read_bytes()).splitlines() if (r:=json.loads(ln))}
    for s in ('','transfer'):
        assert (ROOT/s/'prediction_lock.json').exists()
    for s in ('','transfer'):
        folder=ROOT/s;rows=read((folder/'scores.json.gz').relative_to(ROOT));ids=read((folder/'roster.json').relative_to(ROOT))['ids']
        obs={};pending={};discrep=[]
        for r in rows:
            i,a=r['id'],r['arm'];et=ep.get(i.split('/')[-1]);entry=rs[i]['entry_point']
            if not et or et['entry_point']!=entry:discrep.append(i);continue
            if r['patch_sha'] is None:
                obs[i,a]={'status':'invalid_edit'};continue
            path=folder/'artifacts'/slug(i)/a/'solution.py';key=(i,r['patch_sha']);assert digest(path.read_bytes())==key[1]
            # Only the trusted evaluation scope receives the installed NumPy package location.
            suite='import sys\nsys.path.append('+repr(str(PathSite(numpy)))+')\n'+et['test']+'\ncheck('+entry+')\n'
            if key not in pending:pending[key]=(path,entry,suite)
        def run(kv):
            key,args=kv
            path=folder/'evalplus_receipts'/slug(key[0])/(key[1]+'.json')
            if path.exists():return key,read(path.relative_to(ROOT))
            result=run_suite(*args)
            if isinstance(result.get('detail'),str) and result['detail'] in ('ModuleNotFoundError','ImportError'):result['infrastructure_review_required']=True
            save(path.relative_to(ROOT),result);return key,result
        with concurrent.futures.ThreadPoolExecutor(3) as pool:seen=dict(pool.map(run,pending.items()))
        report_rows=[]
        for r in rows:
            i,a=r['id'],r['arm']
            if i in discrep:continue
            result=seen[i,r['patch_sha']] if r['patch_sha'] else obs[i,a]
            hit=int(result['status']=='pass' and r['action'] in ('applied','control'))
            report_rows.append({'id':i,'arm':a,'base_hit':r['hit'],'plus_hit':hit,'first_plus':int(hit and not r['reread']),'evalplus':result,'patch_sha':r['patch_sha']})
        by={(r['id'],r['arm']):r for r in report_rows}
        def report(sub):
            if not sub:return None
            out={}
            for a in (*ARMS,'canonical','buggy'):
                ds=[by[i,a] for i in sub]
                out[a]={'plus_solves':sum(r['plus_hit'] for r in ds),'first_solves':sum(r['first_plus'] for r in ds),'base_pass_plus_fail':sum(r['base_hit'] and not r['plus_hit'] for r in ds),
                       'base_fail_plus_pass':sum(r['plus_hit'] and not r['base_hit'] for r in ds),'status':dict(collections.Counter(r['evalplus']['status'] for r in ds))}
            return {'n':len(sub),'arms':out,'paired_vs_center':{e:paired([by[i,'bundle'][e] for i in sub],[by[i,'center'][e] for i in sub]) for e in ('plus_hit','first_plus')}}
        seen_ids=[i for i in ids if i not in discrep];valid=[i for i in seen_ids if by[i,'canonical']['plus_hit'] and not by[i,'buggy']['plus_hit']]
        save((folder/'evalplus_rows.json.gz').relative_to(ROOT),report_rows)
        result={'primary':report(seen_ids),'sensitivity':report(valid),'exclusions':sorted(set(discrep)),'physical_runs':len(seen),'numpy':numpy.__version__}
        save((folder/'evalplus_results.json').relative_to(ROOT),result);print(s or 'primary',len(seen),result['primary']['arms'],flush=True)
def PathSite(np):
    return pathlib.Path(np.__file__).resolve().parent.parent
if __name__=='__main__':main()
