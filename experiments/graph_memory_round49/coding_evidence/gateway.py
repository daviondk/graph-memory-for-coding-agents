"""Loopback capability-scoped source gateway. No shell, arbitrary code, tests or network execution."""
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import PurePosixPath
import difflib,re,subprocess
from settings import *
NAME=re.compile(r'woodwork/(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\.py\Z')
class Bad(ValueError):pass
def utc():return datetime.now(timezone.utc).isoformat()
def checked_path(root,rel):
    if not isinstance(rel,str) or not NAME.fullmatch(rel):raise Bad('Expected an existing relative woodwork/*.py path')
    p=(root/PurePosixPath(rel)).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():raise Bad('Unknown source file')
    return p
def positive(x,name):
    if type(x)!=int or x<1:raise Bad(name+' must be a positive integer')
    return x
def clip(s,limit):
    raw=s.encode()[:limit]
    return raw.decode('utf8','ignore')
def sync(folder,state):
    for rel,data in state['edits'].items():
        dst=checked_path(folder/'checkout',rel);raw=data.encode()
        if h(dst.read_bytes())!=h(raw):
            stage=dst.with_name(dst.name+'.gateway-tmp');stage.write_bytes(raw);stage.replace(dst)
def patch(state):
    lines=[]
    for rel,data in sorted(state['edits'].items()):
        after=data.splitlines(keepends=True)
        before=checked_path(B,rel).read_bytes().decode().splitlines(keepends=True)
        for line in difflib.unified_diff(before,after,fromfile='a/'+rel,tofile='b/'+rel,n=3,lineterm='\n'):
            if line.endswith('\n'):lines.append(line.replace('\r\n','\n'))
            else:lines.extend([line+'\n','\\ No newline at end of file\n'])
    return ''.join(lines).encode()
def expose(state,text,individual=3600):
    remaining=LIMITS['source_bytes']-state['bytes']
    if remaining<=0:raise Bad('Source-byte budget exhausted')
    rendered=clip(text,min(remaining,individual))
    n=len(rendered.encode());state['bytes']+=n
    return dict(text=rendered,charged_bytes=n,truncated=(rendered!=text))
def budget(state):
    return dict(used=state['counts'].copy(),source_bytes=state['bytes'],limits=LIMITS)
def apply(folder,state,payload):
    op=payload.get('op');root=folder/'checkout'
    if op=='status':return dict(started=state['started'],frozen=state['frozen'],budget=budget(state))
    if state['frozen']:
        if op=='finish':return state['frozen']
        raise Bad('Patch is frozen')
    if op=='start':
        if state['started']:return dict(already_started=True,budget=budget(state))
        state['started']=True
        state['bytes']+=(folder/'memory.txt').stat().st_size
        return dict(issue=ISSUE.read_text(encoding='utf8'),memory=(folder/'memory.txt').read_bytes().decode(),
                    memory_bytes=(folder/'memory.txt').stat().st_size,budget=budget(state))
    if not state['started']:raise Bad('Call start first')
    if op=='finish':
        b=patch(state);(folder/'change.patch').write_bytes(b)
        touched=sorted(rel for rel,text in state['edits'].items() if text.encode()!=checked_path(B,rel).read_bytes())
        state['frozen']=dict(patch_sha256=h(b),patch_bytes=len(b),files=touched,frozen_utc=utc(),budget=budget(state))
        return state['frozen']
    if op not in ('list','search','read','edit'):raise Bad('Unknown operation')
    if state['counts'].get(op,0)>=LIMITS[op]:raise Bad('Operation budget exhausted')
    state['counts'][op]=1+state['counts'].get(op,0)
    if op=='list':
        files='\n'.join(sorted(p.relative_to(root).as_posix() for p in (root/'woodwork').rglob('*.py')))
        return dict(**expose(state,files),budget=budget(state))
    if op=='search':
        literal=payload.get('literal')
        if not isinstance(literal,str) or not 2<=len(literal)<=80 or '\n' in literal or '\r' in literal or '\0' in literal:raise Bad('Use one literal of 2–80 characters')
        rel=payload.get('path');scope='woodwork' if rel is None else checked_path(root,rel).relative_to(root).as_posix()
        found=subprocess.run(['rg','-F','-n','--with-filename','--sort','path','--no-heading','--color','never','--glob','*.py',
            '--max-count','10','--',literal,scope],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
        if found.returncode not in (0,1):raise Bad('Search did not complete')
        hits=found.stdout.decode('utf8').splitlines()[:10]
        text='\n'.join(s.split(':',1)[0].replace('\\','/')+':'+s.split(':',1)[1] for s in hits)
        v=expose(state,text);return dict(**v,budget=budget(state))
    rel=payload.get('path');p=checked_path(root,rel)
    if op=='read':
        start=positive(payload.get('start'),'start');end=positive(payload.get('end'),'end')
        if end<start or end-start>=100:raise Bad('Read up to 100 consecutive lines')
        lines=p.read_bytes().decode().splitlines(keepends=True)
        if start>len(lines):raise Bad('First requested line exceeds file length')
        v=expose(state,''.join(lines[start-1:end]).replace('\r\n','\n'))
        return dict(path=rel,start=start,**v,budget=budget(state))
    old=payload.get('old');new=payload.get('new')
    if not isinstance(old,str) or not isinstance(new,str) or not old or old==new or not new.strip() and not old.strip():
        raise Bad('Supply a nonempty old string and a different new string')
    if max(len(x.encode()) for x in (old,new))>8000 or '\0' in old+new:raise Bad('Replacement exceeds input limit')
    if rel not in state['edits'] and len(state['edits'])>=LIMITS['files']:raise Bad('File budget exhausted')
    data=p.read_bytes().decode()
    old=old.replace('\r\n','\n');new=new.replace('\r\n','\n')
    matches=list(re.finditer(r'\r?\n'.join(re.escape(s) for s in old.split('\n')),data))
    if len(matches)!=1:raise Bad('Exact old text must occur once; found '+str(len(matches)))
    m=matches[0];newline='\r\n' if '\r\n' in (m.group() if '\n' in m.group() else data) else '\n'
    edited=data[:m.start()]+new.replace('\n',newline)+data[m.end():]
    state['edits'][rel]=edited
    return dict(path=rel,sha256=h(edited.encode()),budget=budget(state))
def dispatch(folder,payload):
    state=load(folder/'session.json');sync(folder,state)
    nonce=payload.get('request_id')
    if nonce is not None:
        if not isinstance(nonce,str) or not re.fullmatch('[A-Za-z0-9_-]{1,40}',nonce):return 400,{'error':'Invalid request_id'}
        for event in state['logs']:
            previous=event['request']
            if previous.get('request_id')==nonce:
                if previous!=payload:return 409,{'error':'request_id already used'}
                return event['code'],event['response']
    try:resp=apply(folder,state,payload);code=200
    except (Bad,UnicodeError,subprocess.TimeoutExpired) as e:resp=dict(error=str(e),budget=budget(state));code=400
    state['logs'].append(dict(seq=len(state['logs'])+1,utc=utc(),request=payload,response=resp,code=code))
    dump(folder/'session.json',state);sync(folder,state)
    return code,resp
class Handler(BaseHTTPRequestHandler):
    def send_json(self,code,v):
        b=json.dumps(v,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        self.send_json(200,{'ready':True}) if self.path=='/health' else self.send_json(404,{'error':'Unknown route'})
    def do_POST(self):
        entry=self.server.access.get(self.path)
        if not entry:return self.send_json(404,{'error':'Unknown route'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>24000:raise ValueError()
            p=json.loads(self.rfile.read(n).decode('utf8'))
            if not isinstance(p,dict):raise ValueError()
        except (ValueError,UnicodeError):return self.send_json(400,{'error':'Invalid UTF-8 JSON object'})
        try:code,body=dispatch(entry,p)
        except Exception:return self.send_json(500,{'error':'Gateway internal failure'})
        return self.send_json(code,body)
    def log_message(self,*args):pass
if __name__=='__main__':
    m=load(P/'assignment.json');assert sha(P/'assignment.json')==load(D/'handoff-seal.json')['assignment']
    with HTTPServer(('127.0.0.1',PORT),Handler) as server:
        server.access={'/v1/'+token:P/v['label'] for token,v in m.items()}
        server.serve_forever()
