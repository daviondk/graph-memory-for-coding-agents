"""Input-only replay: emit each memory state at an empty search, before accepting the following message."""
import collections,gzip,hashlib,json,posixpath,re,shlex,sys
from pathlib import Path
D=Path(__file__).resolve().parent
R12=D.parents[1]/'graph_memory_round12/negative_external'
sys.path.insert(0,str(R12))
import extract as ext
V=ext.V
def h(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
def get(n):
    p=D/n
    return json.loads(gzip.decompress(p.read_bytes()) if str(n).endswith('.gz') else p.read_bytes())
def save(n,v):
    p=D/n
    if str(n).endswith('.gz'):p.write_bytes(gzip.compress(enc(v),mtime=0))
    else:p.write_text(json.dumps(v,ensure_ascii=True,indent=1),encoding='utf8')
def shown(row):
    x=row.get('extra',{});s=ext.EXIT.fullmatch(row.get('content',''));rc=x.get('returncode');raw=x.get('raw_output')
    if type(rc)!=int or not s or int(s[1])!=rc or x.get('exception_info') or not isinstance(raw,str):return None,''
    if not raw.strip() and not s[2].strip():return rc,''
    show=s[2].strip('\r\n')
    if show==raw.strip('\r\n'):return rc,show
    # A trace can retain a longer pre-truncation response. Only shared lines reached the actor.
    actual=set(raw.splitlines());return rc,'\n'.join(l for l in show.splitlines() if l in actual)
SAFE_SUFFIX=re.compile(r'\s*\|\s*(?:head|tail)(?:\s+(?:-\d+|-n\s+\d+))?\s*$')
PATH_PREFIX=re.compile(r'^(?P<p>(?:/|\./)?[A-Za-z0-9_./-]+\.py)(?P<del>[:\-])(?:\d+[:\-])?(?P<body>.*)')
def parse_cmd(cmd):
    original=cmd.strip();cwd='/testbed'
    lead=re.match(r'^cd\s+([\'"]?)([A-Za-z0-9_./-]+)\1\s*&&\s*(.*)$',original,re.S)
    if lead:cwd=posixpath.normpath(posixpath.join(cwd,lead[2]));original=lead[3]
    original=SAFE_SUFFIX.sub('',original.strip())
    if any(t in original for t in ['\n','&&','||',';','>','<','\x60','$(']):return None
    try:words=shlex.split(original)
    except ValueError:return None
    if not words or any(t=='|' for t in words):return None
    if words[:2]==['git','grep']:return cwd,'grep',words[2:]
    return cwd,words[0],words[1:]
def inspect(cmd,visible,repo):
    spec=parse_cmd(cmd)
    if spec is None or not visible.strip():return []
    cwd,tool,args=spec
    if tool not in ('cat','sed','head','tail','nl','grep','rg'):return []
    if re.search(r'\b(No such file or directory|Is a directory|Permission denied|command not found|unrecognized option|invalid (?:option|regular expression))\b',visible[:250],re.I):return []
    def normalize(p):
        rr,f=ext.scope(p,cwd,ext.source(repo))
        return (rr,f) if rr and f.endswith('.py') and f!='.' and not f.startswith('.git/') else None
    paths=[normalize(p) for p in args if p.endswith('.py') and not p.startswith('-')]
    paths=[p for p in paths if p];unique=set(paths)
    # Direct searches are attributed to one .py only if there is exactly one literal file argument
    # in final position. For directories require a repository path on the actual output line.
    if len(unique)==1 and args and normalize(args[-1]) in unique:
        root,path=paths[0]
        lines=visible.splitlines()
        # grep -l, cat-like binary errors, or bare filenames do not count as a source excerpt.
        if tool in ('grep','rg') and (any(re.fullmatch(r'-[A-Za-z]*[lL][A-Za-z]*',x) for x in args) or not any(l.strip() not in {args[-1],path} for l in lines)):return []
        return [(root,path,'grep-file' if tool in ('grep','rg') else 'read',lines)]
    if tool not in ('grep','rg'):return []
    by=collections.defaultdict(list)
    for l in visible.splitlines()[:450]:
        m=PATH_PREFIX.match(l)
        if not m:continue
        p=normalize(m['p'])
        if p and m['body'].strip() and (p in by or len(by)<32):by[p].append(m['body'])
    return [(rr,p,'grep-list',v) for (rr,p),v in by.items()]
def excerpt(lines):
    # Keep first and last displayed nonempty lines plus local declarations to represent long file views.
    valid=[re.sub(r'^[ \t]*[0-9]+[:\t ]','',s)[:190] for s in lines if s.strip()]
    decl=[i for i,s in enumerate(valid) if re.match(r'^\s*(?:def|async def|class|from|import)\s',s)]
    idx=sorted(set([*range(min(5,len(valid))),*decl[:7],*range(max(0,len(valid)-3),len(valid))]))
    return '\n'.join(valid[i] for i in idx)[:1100]
def calls(messages):
    # Generator yields the matching current observation only. The future is read on next().
    pending={};idx=0
    for mi,m in enumerate(messages):
        if m.get('role')=='assistant':
            for tc in m.get('tool_calls') or []:
                fn=tc.get('function') or {};arg=fn.get('arguments');cid=tc.get('id')
                try:a=json.loads(arg) if isinstance(arg,str) else arg
                except ValueError:continue
                if cid and fn.get('name')=='bash' and isinstance(a,dict) and isinstance(a.get('command'),str):pending[cid]=(mi,a['command'])
        elif m.get('role')=='tool' and m.get('tool_call_id') in pending:
            ai,cmd=pending.pop(m['tool_call_id'])
            yield idx,mi,m['tool_call_id'],cmd,m
            idx+=1
def anchor(cmd,row,repo,attest):
    if not ext.SEARCH.search(cmd) or (not attest and not cmd.lstrip().startswith('cd /')):return
    rc,out=shown(row)
    if rc!=1 or out:return
    if row.get('extra',{}).get('raw_output','').strip() or re.search(r'(?:^|\s)-m\s*0\b',cmd):return
    k,why=ext.parse(cmd,'/testbed',ext.source(repo))
    return k
def sample(rec):
    raw=(V/'benchmark'/rec['file']).read_bytes();assert h(raw)==rec['sha']
    msgs=json.loads(raw)['messages']
    start=next(m['content'] for m in msgs if m['role']=='user');issue=start.partition('</pr_description>')[0].split('<pr_description>')[-1].removeprefix('\nConsider the following PR description:\n').strip()
    attest='/testbed (this is the working directory' in start or 'working directory is /testbed' in start
    memory=collections.defaultdict(dict);elapsed=0
    for idx,mi,cid,cmd,row in calls(msgs):
        k=anchor(cmd,row,rec['repo'],attest)
        if k:
            docs={p:{**d,'evidence':list(d['evidence'])} for p,d in memory[k['root']].items()}
            if k['scope'].endswith('.py') and k['scope'] not in docs:docs[k['scope']]={'last':-1,'read':-1,'direct':-1,'support':0,'snip':'','evidence':[]}
            yield {'id':rec['iid']+'|'+cid,'iid':rec['iid'],'repo':rec['repo'],'index':idx,'message':mi,'issue':issue[:1000],'key':k,'docs':docs}
        rc,out=shown(row)
        if rc!=0:continue
        for root,p,kind,lines in inspect(cmd,out,rec['repo']):
            db=memory[root];d=db.setdefault(p,{'last':-1,'read':-1,'direct':-1,'support':0,'snip':'','evidence':[]})
            d['last']=idx;d['support']+=1
            if kind=='read':d['read']=idx
            if kind!='grep-list':d['direct']=idx
            snippet=excerpt(lines)
            if snippet:d['snip']=(d['snip']+'\n'+snippet).strip()[-3072:]
            d['evidence']=(d['evidence']+[[idx,cid,kind,h(snippet.encode())[:16]]])[-5:]
            while len(db)>64:del db[min(db,key=lambda file:(db[file]['last'],file))]
def main():
    roster=ext.get(R12/'roster.json');rows=[]
    for rec in roster:rows.extend(sample(rec))
    assert len({r['id'] for r in rows})==len(rows)
    repos=sorted({r['repo'] for r in roster},key=lambda v:h(('R13-dev-after-miss|'+v).encode()))
    save('inputs.json.gz',rows);save('roster.json',roster)
    save('input.lock.json',{'sources':h((R12/'roster.json').read_bytes()),'parser':h((R12/'extract.py').read_bytes()),'split':{'dev':repos[:6],'external':repos[6:]},'study':{n:h((D/n).read_bytes()) for n in ('PROTOCOL_RU.md','prefix.py','inputs.json.gz','roster.json')},'histories':len(roster),'anchors':len(rows),'tasks_with_anchors':len(set(r['iid'] for r in rows))})
    print(get('input.lock.json'))
if __name__=='__main__':main()
