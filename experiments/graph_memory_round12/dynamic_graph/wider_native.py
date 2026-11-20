import hashlib,json,os,shutil,subprocess,sys,urllib.request,zipfile
from pathlib import Path
from util12 import D,load,dump
TARGET=D/'wide';V='2.8.8';RECENT='3.5'
PY=Path('D:/CodexResearch/x20-bench-workspace/work/graph_memory_round6/repair/env/Scripts/python.exe')
def main():
    TARGET.mkdir(exist_ok=True)
    info=json.load(urllib.request.urlopen('https://pypi.org/pypi/networkx/'+V+'/json',timeout=30))
    wh=next(v for v in info['urls'] if v['filename'].endswith('.whl'));data=urllib.request.urlopen(wh['url'],timeout=30).read();assert hashlib.sha256(data).hexdigest()==wh['digests']['sha256']
    wheel=D/'vendor'/wh['filename'];wheel.write_bytes(data)
    with zipfile.ZipFile(wheel) as z:
        assert all(not Path(f).is_absolute() and '..' not in Path(f).parts for f in z.namelist());z.extractall(D/'vendor'/V)
    dump(TARGET/'release.json',{'sha':wh['digests']['sha256'],'url':wh['url'],'wheel':wh['filename']})
    # Reuse exact instrumentation, collecting only IDs selected in the primary panel.
    collect=(D/'collect.py').read_text(encoding='utf8')
    collect=collect.replace("D=Path(__file__).resolve().parent","D=Path(__file__).resolve().parent").replace("wheel=D/'vendor'/version","wheel=D.parent/'vendor'/version")
    script=TARGET/'collect_old.py';script.write_text(collect,encoding='utf8')
    env=os.environ.copy();env['PYTHONHASHSEED']='0';env['PYTHONIOENCODING']='utf8'
    proc=subprocess.run([str(PY),str(script),V,'list'],env=env,capture_output=True);(TARGET/'collect.log').write_bytes(proc.stdout+proc.stderr);assert proc.returncode==0
    available=set(load(TARGET/f'collection_{V}.json'));roster=load(D/'roster.json')['modules'];select={k:[t for t in ids if t in available] for k,ids in roster.items()}
    dump(TARGET/'roster.json',dict(modules=select,unavailable=[t for ids in roster.values() for t in ids if t not in available]))
    proc=subprocess.run([str(PY),str(script),V,'run'],env=env,capture_output=True);(TARGET/'run.log').write_bytes(proc.stdout+proc.stderr);assert proc.returncode==0
if __name__=='__main__':main()