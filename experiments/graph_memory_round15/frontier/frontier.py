"""Causal path-reference extraction; never execute history tool commands."""
import collections
import gzip
import hashlib
import json
import math
import posixpath
import re
import shlex
import sys
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parent.parent
R=W/'graph_memory_round13'/'reformulation'
G=W/'graph_memory_round14'/'grounded'
sys.path.insert(0,str(R))
import prefix,rank

FORBID=re.compile(r'\b(vulnerabilit(?:y|ies)|exploits?|attacks?|hacking|authentication|authorization|privilege|bypass|sqli|injection|CVE-\d+|denial of service|security|credentials?|penetration|intrusion)\b',re.I)
TOKEN=r'[A-Za-z0-9_./-]+\.py'
FILENAME=re.compile(TOKEN+r'\Z')
ISSUEPAT=re.compile(r'(?<![\w./-])('+TOKEN+r')(?![\w./-])')
QUOTED=re.compile(r'''["'\x60](%s)["'\x60]'''%TOKEN)
TRACE=re.compile(r'^\s*File\s+"('+TOKEN+r')",\s*line\s+\d+')
LOC=re.compile(r'''^\s*(?:file(?:name)?|module location)\s*[:=]\s*["']?('''+TOKEN+r''')["']?\s*$''',re.I)
NO={'.git','.venv','venv','.tox','site-packages','dist-packages','__pycache__'}
def compact(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
def h(b):return hashlib.sha256(b).hexdigest()
def read(p):
    p=Path(p);b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def save(n,v):
    b=compact(v) if n.endswith('.gz') else json.dumps(v,indent=2,sort_keys=True).encode()
    (D/n).write_bytes(gzip.compress(b,mtime=0) if n.endswith('.gz') else b)
def key(path,cwd,repo):
    if not FILENAME.fullmatch(path) or any(x in NO for x in path.split('/')):return
    root,p=prefix.ext.scope(path,cwd,prefix.ext.source(repo))
    if root and p and not p.startswith('.') and p.endswith('.py'):return root,p
def listing(cmd):
    s=prefix.parse_cmd(cmd)
    if not s:return None
    cwd,tool,args=s
    if tool=='git' and args[:1]==['ls-files']:return cwd,'list',None
    if tool=='find':return cwd,'list',None
    if (tool=='rg' and '--files' in args):return cwd,'search_listing',None
    if tool in ('rg','grep') and any(a in ('--files-with-matches','--files-without-match') or re.fullmatch(r'-[A-Za-z]*[lL][A-Za-z]*',a) for a in args):return cwd,'search_listing',None
    if tool=='ls':
        if any(a.startswith('-') and (not re.fullmatch(r'-[aA1F]+',a)) for a in args):return None
        args=[x for x in args if not x.startswith('-')]
        if len(args)>1 or (args and (args[0].endswith('.py') or not re.fullmatch(r'[A-Za-z0-9_./-]+',args[0]))):return None
        return cwd,'list',args[0] if args else '.'
    return None

class State:
    def __init__(self,issue,repo):
        self.repo=repo;self.opened=collections.defaultdict(set);self.front=collections.defaultdict(dict);self.count=collections.Counter()
        items=[]
        for m in ISSUEPAT.finditer(issue):
            if '/' in m[1]:
                items.append((m[1],'/testbed','issue',m[1]))
        self.put(-1,'initial_issue',items)
    def put(self,i,cid,items):
        unique={}
        for text,cwd,typ,line in items:
            addr=key(text,cwd,self.repo)
            if addr and addr[1] not in self.opened[addr[0]]:
                unique.setdefault((*addr,typ),line.strip()[:180])
        for (root,p,typ),line in unique.items():
            pool=self.front[root]
            d=pool.setdefault(p,{'first':i,'last':i,'events':0,'sources':{},'recent_call':''})
            if d['recent_call']!=cid:d['events']+=1
            if typ not in d['sources'] and len(d['sources'])<5:
                d['sources'][typ]={'step':i,'call':cid,'line':line}
            d.update(last=i,recent_call=cid)
            self.count['path_source_notices']+=1
        for pool in self.front.values():
            while len(pool)>64:del pool[min(pool,key=lambda p:(pool[p]['last'],p))]
    def update(self,i,cid,cmd,tool):
        rc,out=prefix.shown(tool)
        if rc is None or not out:return
        parsed=prefix.parse_cmd(cmd);cwd=parsed[0] if parsed else '/testbed'
        found=prefix.inspect(cmd,out,self.repo) if rc==0 else []
        for root,p,t,lines in found:
            self.opened[root].add(p);self.front[root].pop(p,None)
        items=[]
        ls=listing(cmd) if rc==0 else None
        for line in out.splitlines():
            txt=line.strip();m=TRACE.match(line) or LOC.match(line)
            if m and (parsed or m[1].startswith('/')):
                items.append((m[1],cwd,'traceback' if TRACE.match(line) else 'file_location',line))
            if ls and FILENAME.fullmatch(txt):
                loc,kind,parent=ls
                p=posixpath.join(parent,txt) if parent is not None else txt
                items.append((p,loc,kind,line))
        for root,p,t,lines in found:
            for line in lines:
                for ref in QUOTED.finditer(line):
                    if '/' in ref[1]:
                        items.append((ref[1],cwd,'source_literal',line))
        self.put(i,cid,items)
    def snap(self,root,docs):
        f={p:o for p,o in self.front.get(root,{}).items() if p not in docs}
        sv={'front':f,'opened':sorted(self.opened.get(root,set()))}
        snap=json.loads(compact(sv))
        return snap

def bm(row,docs):
    query=collections.Counter(rank.tokens(row['issue'])[:120])
    query.update(4*rank.tokens(row['key']['literal']));query.update(2*rank.tokens(row['key']['scope']))
    voc={p:collections.Counter(3*rank.tokens(p)+rank.tokens(d.get('snip',''))) for p,d in docs.items()}
    sizes={p:sum(x.values()) for p,x in voc.items()};avg=(sum(sizes.values())/len(voc) if voc else 0) or 1
    df=collections.Counter(w for x in voc.values() for w in x)
    out={}
    for p,x in voc.items():
        s=0.
        for w,n in query.items():
            f=x.get(w,0)
            if f:s+=min(4,n)*math.log(1+(len(voc)-df[w]+.5)/(df[w]+.5))*2.2*f/(f+1.2*(.25+.75*sizes[p]/avg))
        out[p]=s
    return out

def predict(row,snap):
    old=row['docs'];front=snap['front'];docs={**old,**front}
    prior=rank.calculate(row)[0]['graph'];oldpos={p:1/(1+.35*i) for i,p in enumerate(prior)}
    recent=sorted(docs,key=lambda p:(-docs[p]['last'],p));age={p:1/(1+.35*i) for i,p in enumerate(recent)}
    bm25=bm(row,docs);scaled=rank.normalize(bm25)
    def order(score):return sorted(docs,key=lambda p:(-score[p],-docs[p]['last'],p))
    base={p:.55*scaled[p]+.25*age[p]+.20*oldpos.get(p,0.) for p in docs}
    corroborated={}
    for p,v in front.items():
        ev=v['sources']
        corroborated[p]=any(a!=b and ev[a]['call']!=ev[b]['call'] for a in ev for b in ev)
    keys=sorted(front,key=lambda p:h(('R15-shuffle|'+row['id']+'|'+p).encode()))
    fake={p:corroborated[keys[(i+1)%len(keys)]] for i,p in enumerate(keys)}
    typed=order({p:s+.25*corroborated.get(p,False) for p,s in base.items()})
    shuffle=order({p:s+.25*fake.get(p,False) for p,s in base.items()})
    bm_order=order(bm25);new=[p for p in bm_order if p in front];alt=[]
    for i in range(max(len(new),len(prior))):
        if i<len(prior):alt.append(prior[i])
        if i<len(new):alt.append(new[i])
    rs={'view_graph':prior,'flat_recent':recent,'bm25_all':bm_order,'flat_union':order(base),'typed_union':typed,'shuffled_union':shuffle,'alternating_union':alt,
        'random_all':sorted(docs,key=lambda p:h(('R15-random|'+row['id']+'|'+p).encode()))}
    assert all(len(v)==len(set(v)) and set(v)==(set(old) if m=='view_graph' else set(docs)) for m,v in rs.items())
    return rs,{'bm25':bm25,'flat':base,'corroborated':corroborated,'shuffled':fake}
