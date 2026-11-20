"""Normal shared pytest imports and unchanged release calibration."""
from testmon_pair import *
def main():
    source=(ROOT/'observe.py').read_text(encoding='utf8')
    body=source[source.index('def normalize'):source.index('def main(')]
    roster=json.loads((ROOT/'roster.json').read_text(encoding='utf8'))
    vers={}
    for row in json.loads((ROOT/'sources.json').read_text(encoding='utf8')):vers.setdefault(row['pkg'],[]).append(row['v'])
    for pkg,vs in vers.items():
        for ix,(old,new) in enumerate(zip(vs,vs[1:])):
            out=ROOT/'testmon_normal'/pkg/(old+'--'+new);out.mkdir(parents=True,exist_ok=True)
            if (out/'run.json').is_file():continue
            work=CACHE/'testmon-trials'/('normal-'+pkg+'-'+old+'-'+new+'-'+uuid.uuid4().hex[:6]);work.mkdir(parents=True)
            (work/'workload.py').write_text('import re, itertools, importlib, sys, json\ncanon=lambda v: json.dumps(v,sort_keys=True)\n'+body,encoding='utf8')
            (work/'test_api.py').write_text(TEST.replace('    clean(row["pkg"])\n',''),encoding='utf8')
            save(work/'cases.json',[r for r in roster if r['pkg']==pkg])
            info={}
            stages=[(old,'old')]+([(old,'unchanged')] if ix==0 else [])+[(new,'new')]
            for t,(v,phase) in enumerate(stages):
                sync_source(work,pkg,v,1650000000+86400*t); log=work/'executed.jsonl'
                if log.exists():log.unlink()
                start=time.perf_counter()
                proc=subprocess.run([str(PY),'-B','-m','pytest','-p','testmon.pytest_testmon','--testmon','--disable-warnings','test_api.py'],cwd=work,env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONUTF8':'1','PYTHONHASHSEED':'0','UNICODE_VERSION':'auto','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,timeout=140)
                (out/(phase+'.log')).write_bytes(proc.stdout+proc.stderr)
                if proc.returncode not in (0,5):raise RuntimeError((pkg,v,(proc.stdout+proc.stderr)[-1500:]))
                records=[json.loads(x) for x in log.read_text(encoding='utf8').splitlines()] if log.exists() else []
                info[phase]={'wall_seconds':time.perf_counter()-start,'ret':proc.returncode,'executed':[r[0] for r in records],
                             'oracle_hashes':{k:sha(json.dumps(val,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()) for k,val in records}}
            assert len(info['old']['executed'])==sum(r['pkg']==pkg for r in roster)
            save(out/'run.json',info);print('normal',pkg,old,new,len(info['new']['executed']),flush=True)
if __name__=='__main__':main()

