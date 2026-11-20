from pathlib import Path,PurePosixPath
from collections import defaultdict,Counter
import re,shlex,sys,json,hashlib,gzip,functools
from acquire import D,W,read,rr,write,save,h,stamp
sys.path.insert(0,str(W));from schema_codec import anchor
@functools.lru_cache(100000)
def token(s):return hashlib.blake2b(s.encode('utf8','surrogatepass'),digest_size=16).hexdigest()
NAMED=re.compile(r'^((?:/testbed/|\./)?[A-Za-z_][\w./-]*\.[A-Za-z0-9_]+):(\d+):(.*)$')
NUMBER=re.compile(r'^\s*(\d+)\t(.*)$')
GREP=re.compile(r'^(\d+):(.*)$')
def clean(path,root=True):
    if not isinstance(path,str) or not re.fullmatch(r'[\w./-]+',path) or path.startswith('-'):return ''
    if not root and not path.startswith('/testbed/'):return ''
    p=anchor.rel(path);return p if p and PurePosixPath(p).suffix else ''
def readlines(raw,root):
    if not raw or raw['name']!='bash':return []
    cmd=raw['command'];out=[]
    if not isinstance(cmd,str) or any(x in cmd for x in ('\n',';','|','>','<','&&','||','$(','`')):return out
    try:args=shlex.split(cmd,posix=True)
    except ValueError:return out
    if not args:return out
    tool=args[0];flat={i+j:s for i,_,vs in raw['pieces'] for j,s in enumerate(vs)}
    if tool in ('rg','grep'):
        if not any(x in ('--line-number','-n') or re.fullmatch(r'-[A-Za-z]*n[A-Za-z]*',x) for x in args[1:]):return out
        file=clean(args[-1],root) if len(args)>2 else ''
        for s in flat.values():
            if m:=NAMED.match(s):
                p=clean(m[1],root)
                if p and int(m[2])>0:out.append((p,int(m[2]),m[3],'search_path'))
            elif file and (m:=GREP.match(s)) and int(m[1])>0:out.append((file,int(m[1]),m[2],'search_one'))
        return out
    if len(args)<2:return []
    p=clean(args[-1],root)
    if not p:return []
    if (tool=='cat' and args[1:-1]==['-n']) or (tool=='nl' and args[1:-1] in (['-ba'],['-b','a'])):
        for line in flat.values():
            if (m:=NUMBER.match(line)) and int(m[1])>0:out.append((p,int(m[1]),m[2],'numbered'))
        return out
    lo=1;hi=10**6
    if tool=='sed' and len(args)==4 and args[1]=='-n' and (m:=re.fullmatch(r'(\d+)(?:,(\d+))?p',args[2])):
        lo=int(m[1]);hi=int(m[2] or m[1])
    elif tool=='head' and len(args)==4 and args[1]=='-n' and args[2].isdigit():hi=int(args[2])
    elif tool=='head' and len(args)==2:hi=10
    elif tool=='cat' and len(args)==2:pass
    else:return []
    if lo<1 or hi<lo or not flat or 0 not in flat:return []
    end=raw['raw_length']
    if flat.get(end-1)=='':end-=1
    if end>hi-lo+1 or end<1 or any(i not in flat for i in range(end)):return []
    if any(re.search(r'output.{0,20}(?:truncated|omitted)|<response clipped>|^Observation:',s,re.I) for s in flat.values()):return []
    return [(p,lo+i,flat[i],'literal_range') for i in range(end)]
def delta(prev,state):
    cur={(p,n):token(v[0]) for p,f in state['rebase'].items() for n,v in f.items()}
    return cur,[[p,n,cur.get((p,n))] for p,n in sorted(prev.keys()|cur.keys()) if prev.get((p,n))!=cur.get((p,n))]
def main():
    info=read(D/'source_receipt.json');assert info['pairs']==h((D/'raw_pairs.jsonl.gz').read_bytes())
    save('method_lock.json',dict(utc=stamp(),files={p.name:h(p.read_bytes()) for p in [D/'policy.py',D/'PROTOCOL.md',D/'IMPLEMENTATION.md',D/'source_receipt.json',W.parent.parent/'graph_memory_round4/writer/anchor/run_anchor.py']}))
    tasks=(q for k in range(8) for q in rr(W/f'source_{k}.jsonl.gz'));counts=Counter();valid=[]
    with gzip.open(D/'decisions.jsonl.gz','wt',encoding='utf8') as co,gzip.open(D/'observed.jsonl.gz','wt',encoding='utf8') as ho:
        for (iid,raw),q in zip(rr(D/'raw_pairs.jsonl.gz'),tasks,strict=True):
            assert iid==q['instance'] and len(raw)==len(q['events']);branches=('base','address','offset');states={a:{'rebase':{}} for a in branches};prev={a:{} for a in branches};meta={a:anchor.newmeta() for a in branches};root=True;tested=set()
            for step,(extra,ev) in enumerate(zip(raw,q['events']),1):
                _,args,obs=ev;p=anchor.rel(args.get('path'));printed=anchor.printed(obs);added=readlines(extra,root)
                if extra:
                    cmd=extra['command'];root=False if re.search(r'(?:^|[;&\n])\s*(?:cd|pushd|popd)\b',cmd) else root
                    if re.fullmatch(r'\s*cd\s+/testbed/?\s*',cmd):root=True
                if args.get('command')=='view' and p:
                    for a in ('address','offset'):
                        for n,s in printed.items():
                            v=prev[a].get((p,n));b=prev['base'].get((p,n));key=(a,p,n,v)
                            if v is not None and v!=b and key not in tested:
                                tested.add(key);valid.append([iid,q['official_repo'],step,a,p,n,v==token(s)])
                changes={}
                for a in branches:
                    anchor.anchored_advance(states[a],meta[a],ev,step)
                    if a!='base':
                        for file,n,s,method in added:
                            states[a]['rebase'].setdefault(file,{})[n+int(a=='offset')]=[s,step]
                    prev[a],changes[a]=delta(prev[a],states[a])
                counts.update([method for p,n,s,method in added]);counts['steps']+=1;counts['steps_parsed']+=bool(added)
                write(co,[iid,step,changes])
                # Editor history indexed even when current version drops it. Separate all observed-text runs.
                editor=[]
                for span in anchor.groups(printed):editor.append([p,span[0],[token(printed[n]) for n in span]])
                observed=[];args_text=[]
                if extra:
                    for _,_,vv in extra['pieces']:
                        observed.append([token(x) for x in vv]);norm=[]
                        for x in vv:
                            m=NAMED.match(x) or NUMBER.match(x) or GREP.match(x);norm.append(token(m.groups()[-1] if m else x))
                        observed.append(norm)
                for field in ('old_str','new_str'):
                    s=args.get(field)
                    if isinstance(s,str) and s:args_text.append([token(x) for x in s.split('\n')])
                write(ho,[iid,step,editor,observed,args_text])
    with gzip.open(D/'views.jsonl.gz','wt',encoding='utf8') as g:
        for r in valid:write(g,r)
    save('decision_lock.json',dict(utc=stamp(),files={p:h((D/p).read_bytes()) for p in ('observed.jsonl.gz','decisions.jsonl.gz','views.jsonl.gz')},counts=dict(counts),view_checks=len(valid)))
if __name__=='__main__':main()

