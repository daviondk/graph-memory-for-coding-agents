"""Local native Git calls on natural groups. Each alternative returns the same per-query Boolean vector."""
import ast,collections,fnmatch,re,random,statistics,time
from pathlib import PurePosixPath
from extract import D,get,save,gz,h
from engine import unpack,measure,pathspec,hkey
from cost import pool
def groupid(r):return (r['repo'],r['parent'],r['merge'])
def applies(file,key):
    scope=key['scope']
    return (scope=='.' or file==scope or file.startswith(scope+'/')) and (not key['globs'] or any(fnmatch.fnmatchcase(file.rsplit('/',1)[-1],g) for g in key['globs']))
def pat(k):
    lit=re.escape(k['literal'].encode())
    return re.compile((b'(?<![A-Za-z0-9_])'+lit+b'(?![A-Za-z0-9_])') if k['word'] else lit,(re.ASCII|re.I) if k['oi'] else re.ASCII)
def aggregate(specs):
    if not specs or any(not s for s in specs):return []
    return sorted({item for spec in specs for item in spec})
def diffpath(raw):
    if raw.startswith(b'"'):raw=ast.literal_eval('b'+raw.decode('ascii'))
    if raw==b'/dev/null':return None
    assert raw.startswith(b'b/'),raw[:70]
    return raw[2:].decode('utf8','surrogateescape')
class Commands:
    def __init__(self,repo):
        self.repo=repo;self.calls=0;self.bytes=0
    def execute(self,args,allowed=(0,)):
        output,rc,ns=measure(self.repo,args)
        if rc not in allowed:raise RuntimeError((self.repo,args[:7],rc))
        self.calls+=1;self.bytes+=len(output)
        return output,rc
def batched_grep(c,rev,rows):
    hits=set();groups=collections.defaultdict(list)
    for i,r in rows:
        k=r['key'];key=(tuple(pathspec(k,r['new_scope'])),k['oi'],k['word'])
        groups[key].append((i,r))
    for (spec,fold,word),g in groups.items():
        flags=['grep','-I','-F'];flags+=['-i'] if fold else [];flags+=['-w'] if word else []
        if len(g)==1:
            i,r=g[0];_,rc=c.execute(flags+['-q','-e',r['key']['literal'],rev,'--',*spec],(0,1))
            if rc==0:hits.add(i)
        else:
            patterns={i:pat(r['key']) for i,r in g};args=flags+['-h','--no-color']
            for literal in sorted({r['key']['literal'] for _,r in g}):args+=['-e',literal]
            out,rc=c.execute(args+[rev,'--',*spec],(0,1))
            if rc==0:
                for i,p in patterns.items():
                    if p.search(out):hits.add(i)
    return hits
def diff_flags():return ['diff','--no-renames','--no-textconv','--no-ext-diff']
def group_predict(c,a,b,rows,kind):
    vals=list(enumerate(rows));hints=set()
    specs=aggregate([pathspec(r['key'],r['old_scope']) for r in rows])
    if kind=='scope':
        output,_=c.execute(diff_flags()+['--name-only','-z',a,b,'--',*specs])
        paths=[p.decode('utf8','surrogateescape') for p in output.split(b'\0') if p]
        return {i for i,r in vals if any(applies(p,r['key']) for p in paths)}
    if kind=='pickaxe':
        cache={}
        for i,r in vals:
            k=r['key'];spec=tuple(pathspec(k,r['old_scope']));idx=(k['literal'],spec,k['oi'],k['word'])
            if idx not in cache:
                assert not k['oi'] and not k['word']
                pattern=''.join('\\'+ch if ch in '\\.^$[]()|+*?{}' else ch for ch in k['literal'])
                out,_=c.execute(diff_flags()+['--name-only','-z','-G'+pattern,a,b,'--',*spec])
                cache[idx]=bool(out)
            if cache[idx]:hints.add(i)
        return hints
    output,_=c.execute(diff_flags()+['--no-color','--src-prefix=a/','--dst-prefix=b/','--unified=0',a,b,'--',*specs])
    file=None;in_hunk=False;active=[];pats=[pat(r['key']) for r in rows]
    for ln in output.split(b'\n'):
        if ln.startswith(b'diff --git '):file=None;in_hunk=False;active=[]
        elif not in_hunk and ln.startswith(b'+++ '):
            file=diffpath(ln[4:].rstrip(b'\t'));active=[i for i,r in vals if file and applies(file,r['key'])]
        elif ln.startswith(b'@@ '):in_hunk=True
        elif in_hunk and file and ln.startswith(b'+'):
            for i in active:
                if i not in hints and pats[i].search(ln[1:]):hints.add(i)
    return hints
def run(grp,rows,method):
    start=time.perf_counter_ns();repo,a,b=grp;c=Commands(repo);hints=set()
    if rows:
        if method=='full':out=batched_grep(c,b,list(enumerate(rows)))
        else:
            hints=group_predict(c,a,b,rows,method.split('_')[0])
            out=batched_grep(c,b,[(i,rows[i]) for i in sorted(hints)]) if method.endswith('_verify') or method=='scope' else hints
    else:out=set()
    end=time.perf_counter_ns()
    return dict(wall_ns=end-start,calls=c.calls,bytes=c.bytes,hits=sorted(out),triggers=sorted(hints))
def main():
    records=pool(unpack('outcomes.json.gz'));groups={groupid(r):[] for r in get(D/'revision_pairs.json') if r['relation']=='direct'}
    for v in records:groups[(v['repo'],v['old'],v['new'])].append(v)
    for group,v in groups.items():v.sort(key=hkey)
    arms=['full','scope','exact','pickaxe','exact_verify','pickaxe_verify']
    jobs=[(m,g,j) for m in arms for g in groups for j in range(3)]
    random.Random(525733).shuffle(jobs);raw=[]
    for i,(m,g,j) in enumerate(jobs,1):
        vals=groups[g];exp=[i for i,q in enumerate(vals) if q['oracle']['new']['hit']]
        obs=run(g,vals,m);assert obs['hits']==exp,(m,g,exp,obs)
        raw.append({'method':m,'group':list(g),'n':len(vals),'queries':[hkey(q) for q in vals],'rep':j,**obs})
        if i%300==0:print(i,len(jobs),flush=True)
    gz('batch_rows.json.gz',raw);summaries={}
    for m in arms:
        by={}
        for g,v in groups.items():
            rs=[r for r in raw if tuple(r['group'])==g and r['method']==m];assert len(rs)==3
            by[g]={'n':len(v),'ms':statistics.median(r['wall_ns'] for r in rs)/1e6,'calls':rs[0]['calls'],'bytes':rs[0]['bytes']}
        summaries[m]={}
        for name,grp in [('total',list(by.values())),('zero',[v for v in by.values() if not v['n']]),('one',[v for v in by.values() if v['n']==1]),('multiple',[v for v in by.values() if v['n']>1])]:
            summaries[m][name]={'groups':len(grp),**{k:sum(v[k] for v in grp) for k in ('n','ms','calls','bytes')}}
    gs=[{'group':list(g),'key_count':len(v),'queries':[hkey(r) for r in v]} for g,v in groups.items()]
    save('batch_summary.json',{'histogram':dict(collections.Counter(map(len,groups.values()))),'groups':gs,'result':summaries,'seed':525733,'repeats':3,'protocol':h((D/'BATCH_PROTOCOL_RU.md').read_bytes())})
    print({m:(z['total'],z['multiple']) for m,z in summaries.items()})
if __name__=='__main__':main()
