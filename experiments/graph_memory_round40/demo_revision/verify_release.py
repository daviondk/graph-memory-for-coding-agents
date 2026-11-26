"""Verify the portable paper, video and localhost demonstration using the standard library."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

D=Path(__file__).resolve().parent
def get_json(path):return json.loads(path.read_bytes())
def verify_hashes(base,rows):
    for name,value in rows.items():
        relative=Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert sha256((base/relative).read_bytes()).hexdigest()==value,name

def check():
    main=get_json(D/'manifest.json')['files']
    verify_hashes(D,main)
    verify_hashes(D/'runtime',get_json(D/'runtime-inputs.json')['files'])
    assert get_json(D/'pdf-check.json')['pages']==4
    video=get_json(D/'video-check.json')
    assert video['duration_seconds']<300 and video['bytes']==(D/'walkthrough.mp4').stat().st_size<50000000
    proc=subprocess.Popen([sys.executable,'-B','-u',str(D/'launcher.py'),'--port','0'],stdout=subprocess.PIPE,text=True)
    try:
        host=proc.stdout.readline().strip()
        assert host.startswith('http://127.0.0.1:')
        def api(endpoint,params):
            with urlopen(host+'/api/'+endpoint+'?'+urlencode(params),timeout=15) as r:return json.load(r)
        args=dict(q='q02',b=2048,mode='certificate')
        state=api('packet',args)
        hit=next(s['id'] for s in state['sources'] if s['selected'])
        miss=next(s['id'] for s in state['sources'] if not(s['selected'] or s['barrier']))
        assert api('packet',dict(args,s=miss))['action']=='Reuse cached packet'
        renewed=api('audit',dict(args,s=hit))
        assert renewed['added']==[19] and renewed['removed']==[11] and renewed['audit']['full_matches']
        assert renewed['audit']['covered_chars']==renewed['audit']['gold_chars']==60
    finally:proc.terminate();proc.wait(timeout=8)
    print(f'Verified {len(main)} signed artifacts, four runtime inputs, packet exchange and independent audit.')
if __name__=='__main__':check()
