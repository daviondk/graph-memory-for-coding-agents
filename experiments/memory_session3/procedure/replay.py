"""Sequential file-read memory. Prediction functions don't take the current tool outcome."""
import posixpath
import re
import shlex
from dataclasses import dataclass

SAFE=r'[A-Za-z0-9_./+@-]+'
PATH=re.compile(r'^(?:'+SAFE+r')$')
def pathname(cwd,token):
    if not PATH.fullmatch(token) or token.startswith('-'):return None
    resolved=posixpath.normpath(posixpath.join(cwd,token))
    if not resolved.startswith('/testbed/'):return None
    return resolved

def split_cwd(command):
    text=command.strip()
    if '\n' in text:return '/testbed',text
    m=re.match(r'''^cd\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))\s*&&\s*(.*)$''',text)
    if not m:return '/testbed',text
    path=next(s for s in m.groups()[:3] if s is not None)
    if not PATH.fullmatch(path): return None,text
    return posixpath.normpath(posixpath.join('/testbed',path)),m.group(4).strip()
def tokens(text):
    try:return shlex.split(text)
    except ValueError:return []
@dataclass(frozen=True)
class Read:
    path:str
    lo:int
    hi:int|None
def parse_read(command):
    if not isinstance(command,str):return None
    cwd,body=split_cwd(command)
    if cwd is None or re.search(r'[\n\r\\$;&|<>*?\x60(){}]',body):return None
    parts=tokens(body)
    if len(parts)<2:return None
    path=pathname(cwd,parts[-1])
    if not path:return None
    args=parts[:-1]
    if args[-1:] == ['--']:args=args[:-1]
    if args==['cat']:return Read(path,1,None)
    if args==['head']:return Read(path,1,10)
    if args[0]=='head':
        n=None
        if len(args)==2 and re.fullmatch('-[0-9]+',args[1]):n=int(args[1][1:])
        if len(args)==3 and args[1]=='-n' and args[2].isdigit():n=int(args[2])
        if n and n<=1000000:return Read(path,1,n)
    if len(args)==3 and args[:2]==['sed','-n']:
        m=re.fullmatch(r'(\d+)(?:,(\d+|\$))?p',args[2])
        if m:
            lo=int(m[1]);hi=(lo if not m[2] else (None if m[2]=='$' else int(m[2])))
            if 0<lo<=1000000 and (hi is None or lo<=hi<=1000000):return Read(path,lo,hi)
    return None
def effect(cmd):
    """Conservatively classify observer actions. An unknown command drops all reusable state."""
    if parse_read(cmd):return 'read',()
    cwd,body=split_cwd(cmd)
    if not cwd:return 'unknown',()
    # A unified patch explicitly applied with the standard apply_patch command.
    if re.match(r"^apply_patch\s+<<\s*['\"]?(\w+)['\"]?\s*\n",body):
        ls=body.splitlines()
        term=re.match(r"^apply_patch\s+<<\s*['\"]?(\w+)['\"]?\s*$",ls[0])
        names=[re.match(r'^\*\*\* (?:Update|Delete|Add) File: (.+)$|^\*\*\* Move to: (.+)$',s) for s in ls]
        names=[pathname(cwd,n[1] or n[2]) for n in names if n]
        if term and len(ls)>=4 and ls[1]=='*** Begin Patch' and ls[-2]=='*** End Patch' and ls[-1]==term[1] and names and all(names):return 'edit',tuple(names)
    # Simple read-only commands and safe pipelines; quoted regexes containing shell punctuation
    # can turn conservative and invalidate the cache even though they only searched.
    if re.search(r'[\n\r;\x60$<>&{}]',body):return 'unknown',()
    commands=[tokens(t) for t in body.split('|')]
    for a in commands:
        if not a:return 'unknown',()
        head=a[0]
        if head=='sed':
            if '-i' in a or any(t.startswith('--in-place') for t in a): return 'unknown',()
            if len(a)<3 or a[1]!='-n' or not re.fullmatch(r'[\d,$]+p',a[2]):return 'unknown',()
        elif head=='git':
            if len(a)<2 or a[1] not in ['diff','status','log','show','ls-files','rev-parse','grep']:return 'unknown',()
            if any(t.startswith(('--output','--ext-diff','--textconv','--exec')) for t in a):return 'unknown',()
        elif head in ['rg','grep','head','tail','cat','wc','pwd','ls','nl','sort','uniq','cut','which','whoami']:
            if any(t in ['-o','--output'] for t in a) and head=='sort':return 'unknown',()
            if any(t.startswith(('--pre','--output')) for t in a):return 'unknown',()
        elif head=='find':
            if any(t in ['-exec','-execdir','-delete','-ok','-okdir','-fprint','-fprint0','-fprintf','-fls'] for t in a):return 'unknown',()
        else:return 'unknown',()
    return 'read',()
@dataclass
class Record:
    op:Read
    cmd:str
    text:str
    size:int
    lines:list
    eof:int|None
class Memory:
    """FIFO of successful observed results; retrieval doesn't touch recency."""
    def __init__(self,max_count,max_bytes):
        self.n=max_count;self.b=max_bytes;self.entries=[];self.size=0
        self.peak=0
    def write(self,op,cmd,text):
        size=len(text.encode())
        if size>self.b:return
        parts=text.split('\n')
        lines=[part+'\n' for part in parts[:-1]]
        if parts[-1]:lines.append(parts[-1])
        # Whole-file suffix can establish EOS only after seeing at least one line,
        # except if the requested range starts at 1 (empty whole file).
        eof=None
        if lines or op.lo==1:
            if op.hi is None or len(lines)<op.hi-op.lo+1:eof=op.lo+len(lines)-1
        r=Record(op,cmd,text,size,lines,eof)
        self.entries.append(r);self.size+=size
        while len(self.entries)>self.n or self.size>self.b:
            self.size-=self.entries.pop(0).size
        self.peak=max(self.size,self.peak)
    def flush(self,paths=None):
        self.entries=[] if paths is None else [r for r in self.entries if r.op.path not in paths]
        self.size=sum(e.size for e in self.entries)
    def lookup(self,op,cmd,mode):
        if not op:return None
        records=[r for r in self.entries if r.op.path==op.path]
        for r in reversed(records):
            if ((mode=='literal' and r.cmd==cmd) or (mode!='literal' and r.op==op)):return r.text
        if mode=='contained':
            for r in reversed(records):
                hi=op.hi
                if r.eof is not None:hi=r.eof if hi is None else min(hi,r.eof)
                if hi is None:continue
                if r.eof is not None and op.lo>r.eof:return ''
                if r.op.lo<=op.lo and hi<r.op.lo+len(r.lines):
                    return ''.join(r.lines[op.lo-r.op.lo:hi-r.op.lo+1])
        if mode!='range' or not records:return None
        lines={};eof=None
        for r in records:
            lines.update(enumerate(r.lines,r.op.lo))
            if r.eof is not None:eof=r.eof
        hi=op.hi
        if eof is not None:hi=eof if hi is None else min(hi,eof)
        if hi is None:return None
        if op.lo>hi:return ''
        if hi-op.lo+1>len(lines):return None
        if any(i not in lines for i in range(op.lo,hi+1)):return None
        return ''.join(lines[i] for i in range(op.lo,hi+1))

