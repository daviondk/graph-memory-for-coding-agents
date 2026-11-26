"""Verify four portable consoles, missing and changed dependencies, and invalid requests."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import queue
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

D=Path(__file__).resolve().parent
def get(url):
    assert urlsplit(url).hostname=='127.0.0.1'
    with urlopen(url,timeout=7) as f:return f.read()
def denied(url,code):
    try:get(url)
    except HTTPError as e:
        assert e.code==code,(e.code,url)
        return e.code
    raise AssertionError(url)
def extract(blob,stage):
    with zipfile.ZipFile(BytesIO(blob)) as z:
        names=z.namelist();assert len(names)==len(set(names))
        assert len(names)<300 and sum(x.file_size for x in z.infolist())<96*1024**2
        for n in names:
            p=PurePosixPath(n);assert p.parts and not p.is_absolute() and '..' not in p.parts and '\\' not in n and ':' not in n
            dest=stage/n
            if n.endswith('/'):dest.mkdir(parents=True,exist_ok=True)
            else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(n))
    options=list(stage.rglob('demo.py'));assert len(options)==1
    return options[0].parent

# Add a cooperative Ctrl-C trigger controlled by a temporary marker; the original __main__ and its
# cleanup context managers remain responsible for all child processes.
HARNESS="""import _thread,runpy,sys,threading,time,pathlib
marker=pathlib.Path(sys.argv[1])
def stop():
    while not marker.exists():time.sleep(.05)
    _thread.interrupt_main()
threading.Thread(target=stop,daemon=True).start()
sys.argv=sys.argv[2:]
runpy.run_path(sys.argv[0],run_name='__main__')
"""
@contextmanager
def running(app,cwd):
    marker=cwd/'stop-local-demo'
    proc=subprocess.Popen([sys.executable,'-I','-B','-u','-c',HARNESS,str(marker),str(app/'demo.py'),'--port','0'],cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    first=queue.Queue();threading.Thread(target=lambda:first.put(proc.stdout.readline()),daemon=True).start()
    host=None
    try:
        host=first.get(timeout=18).decode().strip();assert host.startswith('http://127.0.0.1:') and urlsplit(host).port
        yield host
    finally:
        if proc.poll() is None:
            marker.touch()
            if host:
                try:get(host+'/sessions.json')
                except (OSError,HTTPError):pass
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                if host:
                    try:get(host+'/')
                    except OSError:pass
                proc.wait(timeout=6)
        proc.stdout.close();proc.stderr.close()

def run(archive,scratch=None):
    outer=archive.read_bytes()
    with zipfile.ZipFile(BytesIO(outer)) as z:
        embedded=[n for n in z.namelist() if n.startswith('paper_revision/') and n.endswith('.zip')]
        assert len(embedded)<=1
        blob=z.read(embedded[0]) if embedded else outer
    with TemporaryDirectory(dir=scratch) as tmp:
        work=Path(tmp).resolve();app=extract(blob,work/'portable')
        assert not (work/'graph_memory_round39').exists() and not (work/'graph_memory_round40').exists()
        with running(app,work) as host:
            scenes=json.loads(get(host+'/sessions.json'));assert set(scenes)=={'trace','code','context','flow'}
            assert all(urlsplit(x).hostname=='127.0.0.1' for x in scenes.values()) and len(set(scenes.values())|{host})==5
            assert set(scenes.values())<=set(x for x in get(host+'/').decode().split('"') if x.startswith('http://'))
            a=json.loads(get(scenes['code']+'/api/packet?case=changed'));b=json.loads(get(scenes['code']+'/api/audit?case=stale'))
            assert a['baseline']['bytes']==507 and a['span']['bytes']==74 and len(b['selected_mismatch'])==3
            trace=json.loads(get(scenes['trace']+'/api/packet?q=q02&b=2048&mode=certificate'))
            source=next(r['id'] for r in trace['sources'] if r['selected'])
            proof=json.loads(get(scenes['trace']+'/api/audit?q=q02&b=2048&mode=certificate&s='+source))
            assert proof['added']==[19] and proof['removed']==[11] and proof['audit']['gold_chars']==proof['audit']['covered_chars']==60
            context_ids=[]
            for policy in ('file','range','edges','local'):
                tissue=json.loads(get(scenes['context']+'/audit?case=interior&policy='+policy+'&budget=2048'))
                assert tissue['audit']['mismatches']==0
                context_ids.append(tissue['selected'])
            assert context_ids==[[],[],[0],[0,1]]
            flow_groups={}
            for case in ('accumulating','overlap','withdrawn'):
                focus=json.loads(get(scenes['flow']+'/snapshot?case='+case))
                assert 'audit' not in focus
                if case=='withdrawn':
                    assert any(v & ~focus['active'].get(k,0) for k,v in focus['previous'].items())
                count=focus['total']
                for i in range(1,count+1):
                    audit=json.loads(get(scenes['flow']+f'/audit?case={case}&step={i}'))
                    assert audit['step']==i and audit['audit']['matches']
                flow_groups[case]=count
            http=[denied(host+'/does-not-exist',404),denied(scenes['code']+'/api/packet?case=unknown',400),denied(scenes['trace']+'/api/audit?q=q02&b=1&mode=certificate',400),denied(scenes['context']+'/audit?case=unknown&policy=local&budget=2048',400),denied(scenes['flow']+'/audit?case=withdrawn&step=0',400)]
        movie=app/'walkthrough.mp4'
        probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','stream=codec_name,width,height,nb_frames:format=duration',
            '-of','json',str(movie)],capture_output=True,check=True)
        info=json.loads(probe.stdout)
        stream=info['streams'][0]
        duration=float(info['format']['duration'])
        assert 0 < duration <= 300 and movie.stat().st_size < 50_000_000
        assert int(stream['nb_frames'])>1 and min(stream['width'],stream['height'])>=360
        subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(movie),
                        '-map','0:v:0','-f','null','-'],capture_output=True,check=True)
        video={'duration_seconds':duration,'codec':stream['codec_name'],
               'frames':int(stream['nb_frames']),'resolution':[stream['width'],stream['height']],
               'bytes':movie.stat().st_size,'sha256':sha256(movie.read_bytes()).hexdigest(),'decoded_all':True}
        before=(app/'app-inputs.json').read_bytes();negative=[]
        for name,mut in [('apps/trace/runtime/reader.sqlite','missing'),('apps/code/witness.sqlite','altered'),('apps/context/reader.sqlite','missing'),('apps/flow/flow.sqlite','altered')]:
            p=app/name;original=p.read_bytes()
            if mut=='missing':p.unlink()
            else:p.write_bytes(original[:-1]+bytes([original[-1]^1]))
            try:
                fail=subprocess.run([sys.executable,'-I','-B',str(app/'demo.py'),'--port','0'],cwd=work,capture_output=True,timeout=10)
                assert fail.returncode!=0 and b'http://127.0.0.1:' not in fail.stdout and p.name.encode() in fail.stderr,(name,fail.returncode)
            finally:p.write_bytes(original)
            negative.append([name,mut,'rejected_before_serving'])
        assert before==(app/'app-inputs.json').read_bytes()
    return dict(candidate_sha256=sha256(blob).hexdigest(),real_consoles=4,flow_groups=flow_groups,video=video,context_selected=context_ids,code_packet_bytes=[507,74],stale_selected_lines=3,trace_removed_added=[11,19],trace_coverage=[60,60],invalid_request_codes=http,unavailable_runtime=negative,isolated_imports=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--scratch',type=Path);args=ap.parse_args()
    result=run(args.archive,args.scratch)
    if args.out:
        raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
        if args.out.exists():assert args.out.read_bytes()==raw
        else:args.out.write_bytes(raw)
    print(json.dumps(result))
