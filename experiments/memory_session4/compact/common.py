from pathlib import Path
from collections import Counter,defaultdict
import gzip,hashlib,json,re
ROOT=Path(__file__).resolve().parent
def emit(x):return json.dumps(x,separators=(',',':'),ensure_ascii=False)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(p):
    with gzip.open(p,'rt',encoding='utf8') as f:
        for ln in f:yield json.loads(ln)
def src(k):return rows(ROOT/'source'/f'{k}.jsonl.gz')
def rel(path):
    if not isinstance(path,str):return ''
    p=path.removeprefix('/testbed/').removeprefix('./')
    return '' if p.startswith('/') or '..' in p.split('/') or not p else p
LINE=re.compile(r'^ *([0-9]+)\t(.*)$')
def printed(text):
    out={}
    for ln in text.replace('\r\n','\n').split('\n'):
        m=LINE.match(ln)
        if m and int(m[1])>0:out[int(m[1])]=m[2]
    return out
def success(kind,path,feedback):
    return (kind=='str_replace' and bool(re.search(r'(?:The file .*? has been edited\.|successfully replaced)',feedback[:1300],re.I)))
def groups(lines):
    chunk=[]
    for n in sorted(lines):
        if chunk and n!=chunk[-1]+1:
            yield chunk;chunk=[]
        chunk.append(n)
    if chunk:yield chunk
def update_literal(mem,old,new,printed_now,t):
    found=[]
    for ns in groups(mem):
        block='\n'.join(mem[i][0] for i in ns);idx=block.find(old)
        if idx!=-1:
            if block.find(old,idx+1)!=-1:return {}
            found.append((ns,block,idx))
    if len(found)!=1:return {}
    ns,block,idx=found[0]
    before=block[:idx];start=ns[0]+before.count('\n');end=start+old.count('\n')
    changed=block[:idx]+new+block[idx+len(old):];delta=new.count('\n')-old.count('\n')
    fresh={}
    for i,(txt,age) in mem.items():
        if not (ns[0]<=i<=ns[-1]):fresh[i+(delta if i>ns[-1] else 0)]=(txt,age)
    for j,txt in enumerate(changed.split('\n'),ns[0]):
        if j<start:age=mem[j][1]
        elif j>end+delta:age=mem[j-delta][1]
        else:age=t
        fresh[j]=(txt,age)
    if any(i in fresh and fresh[i][0]!=s for i,s in printed_now.items()):return {}
    return fresh
def advance(states,meta,event,t):
    name,args,obs=event
    if not isinstance(args,dict):return
    if name=='bash':
        meta['bash']=args.get('command','');meta['bash_t']=t;return
    if name not in ('str_replace_editor','str_replace_based_edit_tool','edit_file'):return
    action=args.get('command','');p=rel(args.get('path'));lines=printed(obs) if p else {}
    if not p:return
    changed=success(action,p,obs)
    if action in ('insert','undo_edit','create'):
        # Conservative: for unsupported edit commands, even an unclassified result clears all known text.
        for ss in states.values():ss.pop(p,None)
    for mode,ss in states.items():
        old=ss.get(p,{})
        if changed:
            if mode=='rebase' and isinstance(args.get('old_str'),str) and args['old_str'] and isinstance(args.get('new_str',''),str):
                old=update_literal(old,args['old_str'],args.get('new_str',''),lines,t)
            elif mode!='stale':old={}
        if lines:
            old.update({i:(s,t) for i,s in lines.items()})
        if old:ss[p]=old
        else:ss.pop(p,None)
    if changed:meta['edited'][p]=t
    if lines:
        meta['paths'][p]=t;meta['visits'][p]+=1; meta['center'][p]=(min(lines)+max(lines))*.5
def newmeta():return {'paths':{},'visits':Counter(),'center':{},'edited':{},'bash':'','bash_t':-1}
def pages(mem):
    allp=[]
    for p,lines in mem.items():
        for nums in groups(lines):
            buf=[]
            for n in nums:
                if buf and (n-1)//12!=(buf[-1]-1)//12:
                    allp.append(page(p,buf,lines));buf=[]
                buf.append(n)
            if buf:allp.append(page(p,buf,lines))
    return allp
def page(p,ns,lines):
    return (p,ns[0],ns[-1],max(lines[n][1] for n in ns),'\n'.join(lines[n][0] for n in ns))
def signal(issue,cmd):
    words=lambda s:{x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z_0-9]{2,}',s) if x.lower() not in STOP}
    issue=issue.replace('\r','')
    if '<pr_description>' in issue:issue=issue.partition('<pr_description>')[2].partition('</pr_description>')[0]
    return words(issue[:9000]),words(str(cmd)[-800:])
STOP=set('the for from a import and that with you return def this class your have code with self none true false previously following issue task test tests python problem step change changes expected current repository reproduce implementation feature update above either string path view find bash sed grep testbed cat please would use should but not all assert in when need fix example available requirements instructions method which where does cannot when under file type only before after behavior error new existing make project run works output support description'.split())

