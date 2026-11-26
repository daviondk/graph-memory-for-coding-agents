"""Collect and independently parse every test status in a fresh official image per arm."""
from base64 import b64decode,b64encode
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import argparse,gzip,json,subprocess,xml.etree.ElementTree as ET
from grade_locked import IMAGE
D=Path(__file__).resolve().parent
WORKER="""import base64,json,pathlib,subprocess,sys,tempfile
data=json.load(sys.stdin)
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp)
 check=lambda args:subprocess.run(args,check=True,capture_output=True)
 check(['git','reset','--hard','HEAD'])
 for k in ('candidate','tests'):
  patch=base64.b64decode(data[k])
  if patch:
   f=p/(k+'.diff');f.write_bytes(patch)
   check(['git','apply','--3way','--recount','--ignore-space-change','--whitespace=nowarn',str(f)])
 dest=p/'suite.xml'
 run=subprocess.run(['python','-B','-m','pytest','-q','-rA','--tb=line','--color=no','-p','no:cacheprovider','-W','ignore::DeprecationWarning','--junitxml',str(dest),'woodwork/tests/accessor'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 print(json.dumps(dict(exit=run.returncode,log=base64.b64encode(run.stdout).decode(),xml=base64.b64encode(dest.read_bytes()).decode() if dest.is_file() else None)))
"""
def h(raw):return sha256(raw).hexdigest()
def parse(xml):
    tree=ET.fromstring(xml)
    statuses={}
    for node in tree.iter('testcase'):
        attr=node.attrib
        cls=attr['classname'];bits=cls.split('.');where=next((i for i,b in enumerate(bits) if b.startswith('test_')),None)
        if where is None:
            name=cls.replace('.','/')+'::'+attr['name']
        else:
            path='/'.join(bits[:where+1])+'.py'
            if not path.startswith('woodwork/tests/accessor/'):
                path='woodwork/tests/accessor/'+path.split('/')[-1]
            name=path+'::'+'::'.join(bits[where+1:]+[attr['name']])
        state=next((tag.upper() for tag in ('error','failure','skipped') if node.find(tag) is not None),'PASSED')
        state={'FAILURE':'FAILED'}.get(state,state)
        if name in statuses:
            states=set(statuses[name].split('+'))
            assert state not in states and 'PASSED' not in states and state!='PASSED',name
            state='+'.join(sorted(states|{state}))
        statuses[name]=state
    assert statuses
    return statuses
def main():
    cli=argparse.ArgumentParser();cli.add_argument('output',type=Path);args=cli.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);assert not any(args.output.iterdir())
    spec=json.loads(gzip.decompress((D/'inputs/grade-case.json.gz').read_bytes()))
    locked=json.loads((D/'locked.json').read_bytes());official=json.loads((D/'grading/scores.json').read_bytes())['outcomes']
    candidates={key:(D/v['path']).read_bytes() for key,v in locked['cases'].items()}
    assert all(h(raw)==locked['cases'][k]['sha256'] for k,raw in candidates.items())
    summary={};all_states={}
    for k,data in [('base',b''),('reference',spec['patch'].encode()),*candidates.items()]:
        start=perf_counter();js={'candidate':b64encode(data).decode(),'tests':b64encode(spec['test_patch'].encode()).decode()}
        process=subprocess.run(['docker','run','--network','none','--rm','-i','-w','/woodwork',IMAGE,'python','-c',WORKER],
            input=json.dumps(js).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240,check=True)
        response=json.loads(process.stdout);xml=b64decode(response['xml']);log=b64decode(response['log'])
        states=parse(xml);observed=official[k]['registered_statuses']
        assert all(states[n]==s for group in observed.values() for n,s in group.items())
        all_states[k]=states
        for ext,raw in [('xml',xml),('log',log)]:
            (args.output/(k+'.'+ext+'.gz')).write_bytes(gzip.compress(raw,mtime=0))
        summary[k]={'exit':response['exit'],'seconds':round(perf_counter()-start,3),'xml_sha256':h(xml),'log_sha256':h(log),'status':dict(Counter(states.values())),'checked_official':len(spec['FAIL_TO_PASS'])+len(spec['PASS_TO_PASS'])}
    registered=set(spec['FAIL_TO_PASS']+spec['PASS_TO_PASS'])
    for k,states in all_states.items():
        assert set(states)==set(all_states['base'])
        pairs=Counter((s,states[n]) for n,s in all_states['base'].items() if n not in registered)
        summary[k]['outside_registered']={a+'->'+b:n for (a,b),n in pairs.items()}
    raw=(json.dumps(all_states,sort_keys=True,separators=(',',':'))+'\n').encode()
    (args.output/'profiles.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    (args.output/'summary.json').write_bytes((json.dumps(summary,indent=2,sort_keys=True)+'\n').encode())
    print({k:(v['status'],v['outside_registered']) for k,v in summary.items()})
if __name__=='__main__':main()
