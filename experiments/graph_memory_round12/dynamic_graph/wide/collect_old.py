"""Run inside the selected wheel using a pytest-capable CPU interpreter."""
import hashlib,json,os,sys
from pathlib import Path
D=Path(__file__).resolve().parent
MODULES=['shortest_paths/tests/test_unweighted.py','shortest_paths/tests/test_weighted.py','traversal/tests/test_bfs.py','traversal/tests/test_dfs.py','components/tests/test_connected.py','components/tests/test_strongly_connected.py','tests/test_dag.py','flow/tests/test_mincost.py']
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def save(name,x):(D/name).write_text(json.dumps(x,ensure_ascii=False,indent=1),encoding='utf8')
def roster():
    a,b=[json.loads((D/f'collection_{v}.json').read_bytes()) for v in ['3.4.2','3.5']]
    ids={};candidates={}
    for module in MODULES:
        path='networkx/algorithms/'+module
        common=sorted(i for i in set(a)&set(b) if i.split('::')[0]==path)
        candidates[path]=dict(common=len(common),old=sum(x.startswith(path+'::') for x in a),new=sum(x.startswith(path+'::') for x in b))
        ids[path]=sorted(common,key=lambda i:digest('R12-native|'+i))[:8]
        assert len(ids[path])>=4,(path,len(common))
    save('roster.json',dict(modules=ids,counts=candidates))
def execute(version,mode):
    wheel=D.parent/'vendor'/version;os.chdir(wheel);sys.path.insert(0,str(wheel))
    os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONDONTWRITEBYTECODE='1')
    import networkx,pytest
    assert Path(networkx.__file__).resolve().is_relative_to(wheel) and networkx.__version__==version
    class Plugin:
        def __init__(self):
            self.tests=[];self.active=None;self.rows={};self.status={}
            self.cache={}
        def pytest_collection_finish(self,session):
            self.tests=[i.nodeid.replace(chr(92),'/') for i in session.items]
        def profile(self,frame,event,arg):
            if event!='call':return
            code=frame.f_code
            if code not in self.cache:
                file=Path(code.co_filename)
                try:path=file.relative_to(wheel).as_posix()
                except ValueError:path=''
                self.cache[code]=path+'|'+code.co_qualname if path and path.startswith('networkx/') and '/tests/' not in path and '/test_' not in path and not path.endswith('conftest.py') else None
            address=self.cache[code]
            if address:self.active.add(address)
        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_call(self,item):
            self.active=set()
            sys.setprofile(self.profile)
            try:yield
            finally:
                sys.setprofile(None);self.rows[item.nodeid.replace(chr(92),'/')]=sorted(self.active)
        def pytest_runtest_logreport(self,report):
            self.status.setdefault(report.nodeid.replace(chr(92),'/'),{})[report.when]=report.outcome
    plug=Plugin()
    opts=['--rootdir',str(wheel),'--disable-warnings','-p','no:cacheprovider','-q']
    if mode=='list':opts+=['--collect-only']+['networkx/algorithms/'+m for m in MODULES]
    else:
        selected=json.loads((D/'roster.json').read_bytes())['modules']
        opts+=[t for ts in selected.values() for t in ts]
    status=pytest.main(opts,plugins=[plug])
    if mode=='list':
        assert status==0,status;save(f'collection_{version}.json',plug.tests)
    else:
        save(f'trace_{version}.json' if mode=='run' else f'repeat_{version}.json',dict(rows=plug.rows,status=plug.status,exit_code=int(status)))
if __name__=='__main__':
    if sys.argv[1]=='roster':roster()
    else:execute(sys.argv[1],sys.argv[2])