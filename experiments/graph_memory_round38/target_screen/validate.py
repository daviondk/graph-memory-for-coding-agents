"""Run only the statically reviewed, released PyBaMM CPU tests in a private copy of the export."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys,xml.etree.ElementTree as ET
D=Path(__file__).resolve().parent
I='pybamm-team__pybamm-4267'
E=D/'evaluator'/I
V=Path(os.environ.get('VIBE_CHECKOUT','D:/CodexResearch/x20-official-vibe/VibeMemBench'))
sys.path.insert(0,str(V/'scripts/vendor'))
from log_parsers import parse_log_pytest
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf8')
def run(args,cwd,env,log,check=True):
    p=subprocess.run(args,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
    text=p.stdout+'\n'+p.stderr;(E/log).write_text(text,encoding='utf8')
    if check and p.returncode:raise RuntimeError(text[-1100:])
    return p.returncode,text
def validate_candidate(path):
    patch=Path(path).read_bytes()
    if not patch.strip():return
    if len(patch)>200_000:raise ValueError('Candidate patch over 200 kB')
    lines=patch.decode('utf8').splitlines()
    headers=[s for s in lines if s.startswith('diff --git ')]
    if not headers:raise ValueError('Expected a git unified diff')
    for header in headers:
        m=re.fullmatch(r'diff --git a/(pybamm/[A-Za-z0-9_./-]+[.]py) b/(pybamm/[A-Za-z0-9_./-]+[.]py)',header)
        if not m or m[1]!=m[2] or '..' in Path(m[1]).parts:raise ValueError('Only ordinary package source edits accepted')
    if any(s.startswith(('rename ','copy ','old mode','new mode','new file mode','deleted file mode','GIT binary patch')) for s in lines):
        raise ValueError('Unsupported structural change in this restricted evaluation')
def main(candidate=None):
    if candidate:validate_candidate(candidate)
    c=json.loads((E/'case.json').read_text())
    py=D/'evaluator/venv/Scripts/python.exe';site=D/'evaluator/venv/Lib/site-packages';src=D/'blind'/I/'repo'
    temp=D/'evaluator/tmp';temp.mkdir(exist_ok=True)
    env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','COMSPEC','PATHEXT','SYSTEMROOT','SYSTEMDRIVE','WINDIR','USERPROFILE','PROCESSOR_ARCHITECTURE')}
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',TEMP=str(temp),TMP=str(temp),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTEST_ADDOPTS='-n0')
    args=['--no-header','-rA','--tb=line','--color=no','-p','no:cacheprovider','-W','ignore::DeprecationWarning','tests/unit/test_util.py']
    assert ' '.join(['pytest',*args])==c['install_config']['test_cmd']
    f=set(c['FAIL_TO_PASS']); p=set(c['PASS_TO_PASS']);assert not f&p
    out={}; arms=('candidate-'+sha(Path(candidate))[:16],) if candidate else ('base','reference')
    for a in arms:
        work=E/('c'+a.split('-')[-1][:10] if candidate else 'run-'+a)
        if work.exists():raise RuntimeError(f"Already exists {work}; choose a fresh evaluator/run directory")
        shutil.copytree(src,work); run(['git','init','-q'],work,env,a+'-git.txt')
        for patch in ([E/'test_patch.diff', Path(candidate).resolve()] if candidate else ([E/'test_patch.diff'] if a=='base' else [E/'test_patch.diff',E/'patch.diff'])):
            if not patch.read_bytes().strip():continue
            run(['git','apply','--check',str(patch)],work,env,a+'-check.txt')
            run(['git','apply',str(patch)],work,env,a+'-apply.txt')
        if not list(site.glob('pybamm-*.dist-info')):
            run([str(py),'-B','setup.py','dist_info','--output-dir',str(site)],work,env,'metadata-build.txt')
        _,actual=run([str(py),'-B','-c','import pybamm; print(pybamm.__file__)'],work,env,a+'-origin.txt')
        assert str(work).lower() in actual.splitlines()[0].lower()
        xml=E/(a+'.xml')
        ret,text=run([str(py),'-B','-m','pytest','--junitxml',str(xml),*args],work,env,a+'-pytest.txt',False)
        status=parse_log_pytest(text);xml_status={}
        if xml.exists():
            for n in ET.parse(xml).iter('testcase'):
                cl=n.attrib.get('classname','').split('.')[-1];key=args[-1]+'::'+cl+'::'+n.attrib['name']
                xml_status[key]=next((y for x,y in [('failure','FAILED'),('error','ERROR'),('skipped','SKIPPED')] if n.find(x) is not None),'PASSED')
        correct={k:xml_status.get(k)==status.get(k) and k in status for k in f|p}
        out[a]=dict(exit=ret,parsed=status,f2p=sum(status.get(k)=='PASSED' for k in f),p2p=sum(status.get(k)=='PASSED' for k in p),missing=sorted((f|p)-status.keys()),xml_verified=all(correct.values()),log_sha=sha(E/(a+'-pytest.txt')),reviewed_files={k:sha(work/k) for k in ('pybamm/util.py','tests/unit/test_util.py')})
        save(E/((a+'-results' if candidate else 'validation')+'.json'),out)
        print(a,ret,out[a]['f2p'],out[a]['p2p'],out[a]['missing'],out[a]['xml_verified'],flush=True)
if __name__=='__main__':main(*sys.argv[1:])