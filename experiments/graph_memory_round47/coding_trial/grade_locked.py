"""Grade locked submissions in the digest-pinned upstream image, disconnected from the network.

Input JSON has {"cases":{"arm": {"path":"absolute/file.diff","sha256":"..."}, ...}}.
Both candidate payloads are verified before any grader-only column is opened.
"""
import argparse
import base64
from hashlib import sha256
import importlib.util
import json,os
from pathlib import Path
import subprocess,sys,tempfile
from time import perf_counter
from unittest.mock import patch
import gzip
from check_image import IMAGE
from prepare_source import PARQUET,TARGET

D=Path(__file__).resolve().parent
VENDOR={'eval.py':'e580d953b75e5182a66ffd2fecfbf9c756dadd89db767cfd42bd251f956a7108','log_parsers.py':'818560dab8da86cecc31cd9484a0f2b770359e59c51613316a391b58a73885e1','swe_constants.py':'823dd1ef512d363ed5d4dce05d70f22d7f93b25722cda5b0971f17010f5168a5'}
INNER="""import base64,json,sys,subprocess,tempfile,pathlib
d=json.load(sys.stdin)
def call(argv):
 r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 sys.stdout.buffer.write(r.stdout);sys.stdout.buffer.flush()
 return r.returncode
with tempfile.TemporaryDirectory() as t:
 if call(['git','reset','--hard','HEAD']):sys.exit(80)
 for k in ('candidate','tests'):
  data=base64.b64decode(d[k],validate=True)
  if not data and k=='candidate':continue
  f=pathlib.Path(t)/(k+'.diff');f.write_bytes(data)
  if call(['git','apply','-v','--3way','--recount','--ignore-space-change','--whitespace=nowarn',str(f)]):sys.exit(81)
 sys.exit(call(d['pytest']))
"""
def h(z):return sha256(z).hexdigest()
def main():
    c=argparse.ArgumentParser();c.add_argument('lock',type=Path);c.add_argument('output',type=Path);c.add_argument('--benchmark',type=Path,default=None);c.add_argument('--vendor',type=Path,default=D/'inputs/vendor');args=c.parse_args()
    specs=json.loads(args.lock.read_bytes())['cases']
    assert len(specs)>=2 and all(k.isidentifier() and k not in ('base','reference') for k in specs)
    candidates={}
    for key,v in specs.items():
        f=Path(v['path']);f=f if f.is_absolute() else args.lock.resolve().parent/f
        data=f.read_bytes();assert h(data)==v['sha256'] and len(data)<1_000_000
        data.decode('utf8');candidates[key]=data
    assert not args.output.exists() and (args.benchmark is None or h(args.benchmark.read_bytes())==PARQUET)
    for n,v in VENDOR.items():assert h((args.vendor/n).read_bytes())==v
    loader=importlib.util.spec_from_file_location('official_vibe_grading',args.vendor/'eval.py')
    ev=importlib.util.module_from_spec(loader);loader.loader.exec_module(ev)
    if args.benchmark:
        import pyarrow.parquet as pq
        row=pq.read_table(args.benchmark,filters=[('instance_id','=',TARGET)]).to_pylist()[0]
    else:
        row=json.loads(gzip.decompress((D/'inputs/grade-case.json.gz').read_bytes()))
    assert row['base_commit']=='329b1001755452c96dcefcf4a3c799a2463710e0'
    args.output.mkdir(parents=True)
    report={}
    for key,data in [('base',b''),('reference',row['patch'].encode()),*candidates.items()]:
        start=perf_counter()
        def isolated(image,workdir,patch_dir,patch_name,test_patch_name,test_cmds):
            assert image==IMAGE and workdir=='/click' and test_cmds==[row['install_config']['test_cmd']]
            pts=(Path(patch_dir)/test_patch_name).read_text(encoding='utf8')
            assert pts==row['test_patch'].replace('\r\n','\n')
            assert data.decode('utf8').replace('\r\n','\n').strip()==(Path(patch_dir)/patch_name).read_text(encoding='utf8').strip()
            js={'candidate':base64.b64encode(data).decode(),'tests':base64.b64encode(row['test_patch'].encode()).decode(),'pytest':test_cmds[0].split()}
            assert js['pytest'][0]=='pytest' and len(test_cmds)==1
            cmd=['docker','run','--rm','--network','none','-i','-w',workdir,image,'python','-c',INNER]
            p=subprocess.run(cmd,input=json.dumps(js).encode(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
            return p.returncode,p.stdout.decode('utf8','replace')
        with tempfile.TemporaryDirectory(dir=args.output) as private, patch.object(ev,'run_in_container',isolated),patch.object(ev,'LOGS_DIR',Path(private)):
            official=ev.evaluate_instance(row,IMAGE,{'patch':(data.decode() if data.strip() else '\n')})
            raw=Path(official['log_path']).read_text(encoding='utf8');status=ev.get_parser(row['install_config']['log_parser'])(raw)
            f,p=map(set,(row['FAIL_TO_PASS'],row['PASS_TO_PASS']));assert (len(f),len(p),len(f&p))==(1,15,0)
            observed=f|p;complete=all(k in status for k in observed)
            passed=set(official['passed_actual'])
            (args.output/(key+'.log')).write_bytes(raw.encode())
            report[key]=dict(patch_sha256=h(data),test_patch_sha256=h(row['test_patch'].encode()),exit=official['exit_code'],official_exact=official['passed_match'],all_statuses=complete,
                registered_statuses={group:{n:status.get(n,'MISSING') for n in sorted(nodes)} for group,nodes in [('fail_to_pass',f),('pass_to_pass',p)]},
                f2p=[len(f&passed),len(f)],p2p=[len(p&passed),len(p)],unexpected_passed=len(passed-observed),log_sha256=h(raw.encode()),seconds=round(perf_counter()-start,3))
            assert complete,(key,'Incomplete native test collection')
    assert not report['base']['official_exact'] and report['reference']['official_exact'], 'Uncalibrated source/oracle'
    (args.output/'scores.json').write_bytes((json.dumps(dict(image=IMAGE,lock_sha256=h(args.lock.read_bytes()),outcomes=report),indent=2,sort_keys=True)+'\n').encode())
    for k,v in report.items():print(k,v['official_exact'],v['f2p'],v['p2p'])
if __name__=='__main__':main()
