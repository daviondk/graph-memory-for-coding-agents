"""Run the real pytest-testmon plugin on each independent release transition."""
from pathlib import Path
import json, os, shutil, subprocess, sys, time, uuid
from sources import ROOT,CACHE,tree,save,sha
PY=CACHE/'testmon-env/Scripts/python.exe'
TEST='''import json
import pytest
from pathlib import Path
from workload import resolve, value, clean
R=Path(__file__).parent
CASES=json.loads((R/"cases.json").read_text(encoding="utf8"))
@pytest.mark.parametrize("row",CASES,ids=[r["key"] for r in CASES])
def test_api(row):
    clean(row["pkg"])
    try: fn=resolve(row)
    except AttributeError: fn=None
    actual=value(row,fn)
    assert actual[0] in {"return","exception"}
    with (R/"executed.jsonl").open("a",encoding="utf8") as f:
        f.write(json.dumps([row["key"],actual],ensure_ascii=True)+"\\n")
'''
def sync_source(root,pkg,v,when):
    src=tree(pkg,v)/pkg; dst=root/pkg
    for path in list(dst.rglob('*.py')) if dst.exists() else []:
        if not (src/path.relative_to(dst)).is_file():
            assert path.resolve().is_relative_to(root.resolve());path.unlink()
    for f in src.rglob('*.py'):
        dest=dst/f.relative_to(src)
        data=f.read_bytes()
        if not dest.exists() or dest.read_bytes()!=data:
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);os.utime(dest,(when,when))
def main():
    roster=json.loads((ROOT/'roster.json').read_text(encoding='utf8'))
    vers={}
    for r in json.loads((ROOT/'sources.json').read_text(encoding='utf8')):
        if not r.get('skip'):vers.setdefault(r['pkg'],[]).append(r['v'])
    source=(ROOT/'observe.py').read_text(encoding='utf8')
    body=source[source.index('def normalize'):source.index('def main(')]
    for pkg,vs in vers.items():
        for old,new in zip(vs,vs[1:]):
            out=ROOT/'testmon'/pkg/(old+'--'+new);out.mkdir(parents=True,exist_ok=True)
            if (out/'run.json').exists():continue
            work=CACHE/'testmon-trials'/(pkg+'-'+old+'-'+new+'-'+uuid.uuid4().hex[:6]);work.mkdir(parents=True)
            (work/'workload.py').write_text('import re, itertools, importlib, sys, json\ncanon=lambda v: json.dumps(v,sort_keys=True)\n'+body,encoding='utf8')
            (work/'test_api.py').write_text(TEST,encoding='utf8');save(work/'cases.json',[r for r in roster if r['pkg']==pkg])
            info={}
            for t,(v,phase) in enumerate([(old,'old'),(new,'new')]):
                sync_source(work,pkg,v,1650000000+86400*t)
                log=work/'executed.jsonl'
                if log.exists():log.unlink()
                tm=time.perf_counter()
                proc=subprocess.run([str(PY),'-B','-m','pytest','-p','testmon.pytest_testmon','--testmon','-q','--disable-warnings','test_api.py'],cwd=work,env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONUTF8':'1','PYTHONHASHSEED':'0','UNICODE_VERSION':'auto','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,timeout=140)
                (out/(phase+'.log')).write_bytes(proc.stdout+proc.stderr)
                if proc.returncode not in (0,5):raise RuntimeError((pkg,v,(proc.stdout+proc.stderr)[-1500:]))
                records=[json.loads(x) for x in log.read_text(encoding='utf8').splitlines()] if log.exists() else []
                info[phase]={'wall_seconds':time.perf_counter()-tm,'ret':proc.returncode,'executed':[r[0] for r in records],
                             'oracle_hashes':{k:sha(json.dumps(val,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()) for k,val in records}}
            assert len(info['old']['executed'])==sum(r['pkg']==pkg for r in roster)
            save(out/'run.json',info);print('testmon finished',pkg,old,new,len(info['new']['executed']),flush=True)
if __name__=='__main__':main()

