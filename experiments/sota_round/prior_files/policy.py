"""A causal, write-time index of files actually edited in previous sessions."""
import math,re
from collections import Counter,defaultdict
from pathlib import PurePosixPath
from memory_interface import MemorySystem,RetrievedMemory
from memory_systems.demo import EchoMemorySystem
from methods import tokens,clip,TEST_COMMAND,TEST_PASS
EXT={'.py','.pyi','.rs','.ts','.tsx','.jsx','.js','.go','.java','.kt','.kts','.swift','.c','.cc','.cpp','.h','.hpp','.php','.rb','.m','.cs','.scala','.vue','.svelte','.sql','.sh'}
EXCLUDE={'test','tests','testing','spec','specs','fixtures','vendor','vendors','node_modules','dist','build','__tests__','__pycache__','third_party','examples','docs','benchmarks'}
ID=re.compile(r'[A-Za-z_][A-Za-z_0-9]{2,}')
def valid(p):
    pp=PurePosixPath(p)
    return bool(p and p!='/dev/null' and not pp.is_absolute() and '..' not in pp.parts and pp.suffix.lower() in EXT and not set(z.lower() for z in pp.parts)&EXCLUDE and not re.search(r'(^test_|_test\.|[.]tests?[.]|Test[s]?[.])',pp.name))
def parse_diff(text):
    grouped={};key=''
    for l in text.splitlines():
        if l.startswith('diff --git '):key=''
        elif l.startswith('+++ '):
            key=l[4:].split('\t')[0].removeprefix('b/')
            if valid(key):grouped.setdefault(key,[[],[]])
            else:key=''
        elif key and l.startswith('@@'):
            right=l.split('@@')[-1].strip()
            if right and len(grouped[key][0])<4:grouped[key][0].append(right[:120])
        elif key and l.startswith(('+','-')) and not l.startswith(('+++','---')):
            if len(grouped[key][1])<72:
                for i in ID.findall(l):
                    if len(grouped[key][1])>=72:break
                    if i not in grouped[key][1]:grouped[key][1].append(i)
    return grouped
class PriorFiles(MemorySystem):
    def __init__(self):
        self.hist=[];self.unique=set();self.parser=EchoMemorySystem();self.context=None;self.audit={}
    def add(self,session,*,scope):
        self.context=scope.user_id
        steps=self.parser._iter_steps(session.messages);files={};test=''
        for s in steps:
            if s['kind']=='final_patch':files.update(parse_diff(s['output']))
            cmd=s['command'].strip()
            if str(s['returncode'])=='0' and TEST_COMMAND.search(cmd) and not re.search(r'[|;]',cmd) and TEST_PASS.search(s['output']):
                test=clip(cmd,16,220)
        for path,(head,ident) in files.items():
            self.hist.append((session.session_id,path,head,ident,test))
            self.unique.add(path)
    def count(self):return len(self.hist)
    def search(self,query,*,scope,top_k):
        import json
        self.audit={'candidate':[],'single':[],'freq':[],'all_prior':sorted(self.unique),'stored_records':len(self.hist),'stored_text_bytes':sum(len(json.dumps(r,ensure_ascii=False).encode()) for r in self.hist)}
        if not self.hist:return []
        assert scope.user_id==self.context
        freqs=[Counter(tokens(' '.join([path,path,path,*head,*ident]))) for _,path,head,ident,test in self.hist]
        n=len(freqs);avg=sum(c.total() for c in freqs)/n
        df=Counter(t for f in freqs for t in f);q=set(tokens(query));groups=defaultdict(list)
        for j,(sid,path,head,ident,test) in enumerate(self.hist):
            f=freqs[j]; norm=1.2*(.25+.75*f.total()/max(1,avg))
            score=sum(math.log(1+(n-df[t]+.5)/(df[t]+.5))*2.2*f[t]/(f[t]+norm) for t in sorted(q&f.keys()))
            groups[path].append((score,j))
        grades={}
        for path,v in groups.items():
            v.sort(key=lambda t:(-t[0],t[1]));a=[k[0] for k in v[:3]]+[0,0]
            grades[path]={'single':a[0],'freq':len({self.hist[j][0] for _,j in v}),'candidate':a[0]+.35*a[1]+.15*a[2]+.6*math.log1p(len(v))}
        result=[]
        for policy in ['single','freq','candidate']:
            ranked=sorted(groups,key=lambda p:(-grades[p][policy],p))
            top=ranked[0]; _,j=groups[top][0];source=self.hist[j][0];body=[]
            for p in ranked:
                hits=[jj for _,jj in groups[p] if self.hist[jj][0]==source]
                if not hits:continue
                _,_,h,ident,check=self.hist[hits[0]]
                self.audit[policy].append(p)
                symbols=' '.join(dict.fromkeys(h+ident[:10]))
                body.append(p+(' — '+symbols[:170] if symbols else ''))
                if len(body)>=3:break
            if policy=='candidate':
                msg='A previous solver actually edited these files. Historical symbols are search hints; check their current implementations.\\n'+'\n'.join(body)
                if self.hist[j][4]:msg+='\nTest command with observed passing output in that prior session: '+self.hist[j][4]
                result=[RetrievedMemory(id=source+'::files',source_session_id=source,content=clip(msg.replace('\\n','\n')),score=float(grades[top][policy]),metadata={'evidence_kind':'historical_edit'})]
        return result[:top_k]

