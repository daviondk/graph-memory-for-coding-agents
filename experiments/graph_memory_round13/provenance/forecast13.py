"""No oracle, patch, scope label or subsequent prior-query result is loaded."""
import fnmatch,posixpath,re,shlex,time,statistics
from collections import Counter,defaultdict
from common13 import D,R12,sha,digest,dump,read,obs
from extract import pairs,V
from objects import git
from witness import inspect_command
COLS=['trust','always_scan','cwd','pwd','path_exists','last_r12','directory','content','fresh_content','scope_content','fresh_scope_strict','two_scope_files','strict_conflict_veto','prefix_red_flag','verified_red_flag']
def inside(p,k):
    root=k['scope']
    return (root=='.' or p==root or p.startswith(root+'/')) and (not k['globs'] or any(fnmatch.fnmatchcase(posixpath.basename(p),g) for g in k['globs']))
def contains(term,k):
    raw=re.escape(k['literal'].encode())
    if k['word']:raw=b'(?<![A-Za-z0-9_])'+raw+b'(?![A-Za-z0-9_])'
    return bool(re.search(raw,term.encode('utf8',errors='replace'),flags=re.ASCII|(re.I if k['oi'] else 0)))
def single_file(cmd):
    cmd=re.sub(r'^cd\s+[\w./-]+\s*&&\s*','',cmd.strip())
    try:t=shlex.split(cmd)
    except ValueError:return False
    if not t:return False
    if t[0]=='cat':return len(t)==2 and not t[-1].startswith('-')
    if t[0] in ['head','tail','nl']:return (len(t)==2 or len(t)==3 and re.fullmatch(r'-\d+',t[1]) or len(t)==4 and t[1]=='-n' and t[2].isdigit()) and not t[-1].startswith('-')
    return t[0]=='sed' and len(t)==4 and t[1]=='-n' and bool(re.fullmatch(r'\d+(?:,\d+)?p',t[2]))
def directory_names(raw):
    displayed=set()
    for line in raw.splitlines()[:180]:
        y=line.strip().rstrip('/')
        if y and ' ' not in y:displayed.add(y)
        elif re.match(r'^[-dl][rwxstST-]{9}\s',y):displayed.add(y.split()[-1].rstrip('/'))
    return displayed
def normalized(raw):
    return {re.sub(r'^\s*\d+[:\t ]','',line).strip() for line in raw.splitlines()[:180] if len(line.strip())>=20}
def tree(repo,rev):
    start=time.perf_counter_ns();b=git(repo,'ls-tree','-r','-z',rev).stdout;dt=time.perf_counter_ns()-start;files={}
    for row in b.split(b'\0'):
        if not row:continue
        head,path=row.split(b'\t',1);mode,kind,oid=head.split()
        if mode in [b'100644',b'100755'] and kind==b'blob':files[path.decode('utf8','surrogateescape')]=oid.decode()
    return files,dict(kind='tree',repo=repo,obj=rev,bytes=len(b),ns=dt)
def blob(repo,oid):
    start=time.perf_counter_ns();b=git(repo,'cat-file','blob',oid).stdout;dt=time.perf_counter_ns()-start
    lines=set(l.strip() for l in b.decode('utf8',errors='replace').splitlines() if len(l.strip())>=20)
    return (set() if b'\0' in b[:8000] else lines),dict(kind='blob',repo=repo,obj=oid,bytes=len(b),ns=dt)
def main():
    keys=read(R12/'keys.json');roster={r['iid']:r for r in read(R12/'roster.json')};base={r['iid']:r for r in read(R12/'revision_pairs.json')}
    historical={obs(x):x.get('support') for x in read(R12/'provenance.json.gz')};refs={};cache={};work={};out=[];cold=[]
    for iid in sorted({k['iid'] for k in keys}):
        r=roster[iid];repo=r['repo'];rev=base[iid]['parent'];file=V/'benchmark'/r['file'];raw=file.read_bytes()
        assert sha(raw)==r['sha'];refs[r['file']]=sha(raw)
        watched=[(i,c,z['extra']) for i,c,z in pairs(__import__('json').loads(raw)['messages']) if isinstance(z.get('extra'),dict)]
        st,op=tree(repo,rev);tree_id=repo+'@'+rev;work[tree_id]=op
        for note in sorted((q for q in keys if q['iid']==iid),key=lambda q:q['step']):
            start=time.perf_counter_ns();k=note['key'];root=k['root'];e=[];pwd=False;blobs=set();prefixbytes=0
            prior=[r for r in watched if r[0]<note['step']]
            for j,(step,cmd,z) in enumerate(prior):
                if z.get('returncode')!=0 or not isinstance(z.get('raw_output'),str):continue
                text=z['raw_output'];prefixbytes+=len(text.encode('utf8',errors='replace'))+len(cmd.encode())
                if re.fullmatch(r'(?:cd\s+[A-Za-z0-9_./-]+\s*&&\s*)?pwd',cmd.strip()) and text.strip().rstrip('/')==root.rstrip('/'):pwd=True
                for rr,p,kind in inspect_command(cmd,repo):
                    if rr!=root:continue
                    rec=dict(step=step,age=len(prior)-j,path=p,kind=kind,scope=inside(p,k),matched=0,strict=0,prior_positive=False,target_positive=False,conflict=False,blob='',bytes_shown=len(text.encode('utf8',errors='replace')))
                    if kind=='ls':
                        prefix='' if p=='.' else p+'/';names={f[len(prefix):].partition('/')[0] for f in st if f.startswith(prefix)}
                        shown=directory_names(text);rec['matched']=len(names&shown)
                    else:
                        shown=normalized(text);pure=bool(single_file(cmd));rec['single_file']=pure
                        rec['prior_positive']=rec['scope'] and pure and any(contains(v,k) for v in shown)
                        target=set()
                        if p in st:
                            oid=st[p];ident=repo+'@'+oid
                            if ident not in cache:cache[ident],work[ident]=blob(repo,oid)
                            target=cache[ident];blobs.add(ident);rec['blob']=ident
                        shared=target&shown;rec['matched']=len(shared);rec['strict']=sum(len(l)>=32 for l in shared)
                        rec['line_hashes']=[sha(x.encode()) for x in sorted(shared)[:4]]
                        rec['target_positive']=rec['scope'] and pure and any(contains(v,k) for v in shared)
                        rec['conflict']=rec['scope'] and pure and len(shown)>=2 and not shared
                    e.append(rec)
            valid=[x for x in e if x['kind']=='content' and x['matched']>=2];dirs=[x for x in e if x['kind']=='ls' and x['matched']>=3];sc=[x for x in valid if x['scope']];fresh=[x for x in valid if x['age']<=5];strong=[x for x in sc if x['strict']>=3 and x['age']<=5];scope_strict=[x for x in sc if x['strict']>=3]
            conflict=any(x['conflict'] for x in e);red=any(x['prior_positive'] for x in e);verified=any(x['target_positive'] for x in e)
            path=k['scope'];exist=path=='.' or path in st or any(p.startswith(path+'/') for p in st)
            decisions=[True,False,root=='/testbed',pwd,exist,historical.get(obs(note)) in ('directory_names','tracked_file_lines'),bool(dirs),bool(valid),bool(fresh),bool(sc),bool(strong),len({h['path'] for h in sc})>=2,bool(scope_strict) and not conflict,not red,not verified]
            level=5 if strong else 4 if sc else 3 if valid else 2 if dirs else int(pwd)
            selected=strong or sc or valid or dirs;age=min([v['age'] for v in selected],default=1_000_000)
            out.append(dict(id=obs(note),iid=iid,repo=repo,rev=rev,step=note['step'],scope=path,root=root,prior_calls=len(prior),score=[int(not verified),int(not conflict),level,-age],trust=dict(zip(COLS,map(bool,decisions))),prefix_bytes=prefixbytes,evidence=e,tree=tree_id,blob_ids=sorted(blobs),feature_ns=time.perf_counter_ns()-start))
    dump(D/'features.json.gz',out);dump(D/'operations.json',work)
    dump(D/'forecast_lock.json',dict(count=len(out),code={name:digest(D/name) for name in ['PROTOCOL.md','common13.py','forecast13.py']},old_inputs={name:digest(R12/name) for name in ['keys.json','roster.json','revision_pairs.json','provenance.json.gz','witness.py','objects.py','extract.py']},prefix_sources=refs,features=digest(D/'features.json.gz'),operations=digest(D/'operations.json')))
if __name__=='__main__':main()