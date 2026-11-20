import sys
from pathlib import Path
E=Path(__file__).resolve().parent
sys.path.insert(0,str(E.parent))
from common13 import D,W,read,dump,digest,sha
sys.dont_write_bytecode=True
R11=W/'graph_memory_round11'/'negative_actions';sys.path.append(str(R11))
import re,posixpath,time,statistics
from collections import Counter
from forecast13 import contains,inside,normalized,directory_names,single_file
from witness import inspect_command
from git_pairs import git,local
from grade13 import distribution
from replay import grep_run
import numpy as np
def main(which):
    if which=='predict':
        rows=[r for r in read(R11/'keys.json') if r['key']['kind']=='text'];treecache={};objects={};results=[];sources={}
        assert len(rows)==31
        for r in rows:
            iid=r['iid'];repo=r['repo'];base=r['base'];path=R11/'observations'/(iid+'.json.gz');entries=read(path)['steps']; sources[path.name]=digest(path)
            q=r['key'];query=dict(scope=q['scope'],globs=q.get('globs',[]),literal=q['literal'],oi=q.get('ignore_case',False),word=q.get('whole_word',False))
            if (repo,base) not in treecache:
                payload=git(local(repo),'ls-tree','-r','-z',base).stdout;paths={}
                for line in payload.split(b'\0'):
                    if line:
                        head,key=line.split(b'\t',1);mode,kind,oid=head.split();
                        if mode in [b'100644',b'100755'] and kind==b'blob':paths[key.decode('utf8','surrogateescape')]=oid.decode()
                treecache[repo,base]=paths
            files=treecache[repo,base];events=[]
            for j,s in enumerate(entries[:r['step']]):
                if not s:continue
                txt=s.get('raw') if isinstance(s.get('raw'),str) else s.get('seen')
                if not isinstance(txt,str) or not txt.strip():continue
                if re.search(r'(?:No such file or directory|command not found)',txt[:300],re.I):continue
                a=s['args'];cwd=s.get('cwd') or '/testbed';rawpath=None;kind='content';pure=True
                if s['tool']=='str_replace_editor' and a.get('command')=='view':
                    rawpath=a.get('path')
                    if not isinstance(rawpath,str):continue
                    absname=posixpath.normpath(posixpath.join(cwd,rawpath))
                    if not absname.startswith('/testbed/'):continue
                    k=absname[len('/testbed/'):]
                    kind='content' if k in files else 'ls' if any(p.startswith(k+'/') for p in files) else 'content'
                elif s['tool']=='bash':
                    cmd=a.get('command','')
                    if not isinstance(cmd,str):continue
                    enriched=cmd if cwd=='/testbed' or cmd.strip().startswith('cd ') else 'cd '+cwd+' && '+cmd
                    ws=inspect_command(enriched,repo)
                    if len(ws)!=1 or ws[0][0]!='/testbed':continue
                    _,k,kind=ws[0];pure=bool(single_file(cmd))
                else:continue
                shown=normalized(txt);shared=set();count=0;sc=inside(k,query)
                if kind=='ls':
                    prefix='' if k=='.' else k+'/';count=len(directory_names(txt)&{p[len(prefix):].split('/')[0] for p in files if p.startswith(prefix)})
                elif k in files:
                    oid=files[k]
                    if (repo,oid) not in objects:
                        raw=git(local(repo),'cat-file','blob',oid).stdout;objects[repo,oid]={s.strip() for s in raw.decode('utf8',errors='replace').splitlines() if len(s.strip())>=20} if b'\0' not in raw[:8000] else set()
                    shared=shown&objects[repo,oid];count=len(shared)
                events.append(dict(age=r['step']-j,path=k,scope=sc,kind=kind,matched=count,long=sum(len(w)>=32 for w in shared),red=sc and pure and any(contains(v,query) for v in shown),verified_red=sc and pure and any(contains(v,query) for v in shared)))
            files2=[a for a in events if a['kind']=='content' and a['matched']>=2]
            polys=dict(trust=True,always_scan=False,cwd=r['cwd']=='/testbed',directory=any(a['kind']=='ls' and a['matched']>=3 for a in events),content=bool(files2),fresh_content=any(a['age']<=5 for a in files2),scope_content=any(a['scope'] for a in files2),fresh_scope_strict=any(a['scope'] and a['age']<=5 and a['long']>=3 for a in files2),prefix_red_flag=not any(a['red'] for a in events),verified_red_flag=not any(a['verified_red'] for a in events))
            results.append(dict(iid=iid,panel=r['panel'],repo=repo,step=r['step'],base=base,events=events,trust=polys))
        dump(E/'forecasts.json.gz',results);dump(E/'lock.json',dict(raw_sources=sources,code=digest(E/'external13.py'),protocol=digest(E/'PROTOCOL.md'),forecasts=digest(E/'forecasts.json.gz'),native_keys=digest(R11/'keys.json')))
    else:
        lock=read(E/'lock.json');assert lock['forecasts']==digest(E/'forecasts.json.gz') and lock['code']==digest(E/'external13.py')
        rr=read(E/'forecasts.json.gz');old={(r['iid'],r['step']):r for r in read(R11/'oracle.json')};cases=[];ex=[];runtime=[]
        for r in rr:
            o=old[r['iid'],r['step']];clock=time.perf_counter_ns();new=grep_run(r['repo'],r['base'],o['key']);ns=time.perf_counter_ns()-clock
            assert new['valid']==o['old_oracle']['valid'] and new.get('hit')==o['old_oracle'].get('hit')
            item=dict(iid=r['iid'],step=r['step'],repo=r['repo'],panel=r['panel'],valid=new['valid'],hit=new.get('hit'),direct_ns=ns,trust=r['trust']);runtime.append(item)
            if new['valid']:cases.append(item)
            else:ex.append(item)
        ids=np.array([r['iid'] for r in cases]);nt=len(set(ids));boot=np.random.default_rng(13027).integers(0,nt,(10000,nt));y=np.array([r['hit'] for r in cases],bool)
        table={a:distribution(y,np.array([r['trust'][a] for r in cases]),ids,boot,13027) for a in cases[0]['trust']}
        primary=read(D/'features.json.gz')
        dump(E/'results.json',dict(n=len(rr),nvalid=len(cases),tasks=nt,sources=Counter(r['panel'] for r in rr),repos=sorted({r['repo'] for r in rr}),repo_overlap=sorted({r['repo'] for r in rr}&{r['repo'] for r in primary}),n_unsafe=int(y.sum()),invalid=ex,policies=table,direct_ms=sum(r['direct_ns'] for r in runtime)/1e6))
        dump(E/'graded.json.gz',runtime)
if __name__=='__main__':main(sys.argv[1])