"""Descriptive, frozen audit of real code-agent histories. No replay of untrusted commands."""
import argparse, collections, concurrent.futures, datetime, hashlib, json, re, shlex, time
from pathlib import Path
from urllib.parse import quote
import requests
HERE=Path(__file__).resolve().parent
REV='11164976b4f920cdb0d0cd570ca572e49acea1e8'
DATA='Tongyi-ConvAI/VibeMemBench'
SEED='scope-field/20261116/v1'
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def order(name):return hashlib.sha256((SEED+'|'+name).encode()).hexdigest()
def repo(path):return path.split('/')[2]
def fetch(url):
    issues=[]
    for attempt in range(3):
        try:
            r=requests.get(url,timeout=(8,30));r.raise_for_status()
            return r.content,issues
        except requests.RequestException as e:
            issues.append({'at':utc(),'error':str(e)});time.sleep(attempt+1)
    return None,issues
def select():
    raw,err=fetch('https://huggingface.co/api/datasets/'+DATA+'/revision/'+REV)
    if raw is None:raise RuntimeError(err)
    excluded=set(json.loads((HERE/'excluded_repos.json').read_text()))
    groups=collections.defaultdict(list)
    for entry in json.loads(raw)['siblings']:
        path=entry['rfilename']
        if path.startswith('history/python/') and path.endswith('.traj.json') and repo(path) not in excluded:
            groups[repo(path)].append(path)
    candidates=sorted([r for r,v in groups.items() if len(v)>=4],key=order)
    assert len(candidates)>=12
    paths=[p for r in candidates[:12] for p in sorted(groups[r],key=order)[:4]]
    save(HERE/'sample.json',{'created_utc':utc(),'seed':SEED,'revision':REV,'eligible_repositories':len(candidates),'excluded':sorted(excluded),'paths':paths,'index_retrieval_errors':err})
def parse(s):
    if any(x in s.strip() for x in ('\n','\r','`','$(')):return
    try:
        shell=shlex.shlex(s,posix=True,punctuation_chars=';&<>|');shell.whitespace_split=True;shell.commenters=''
        args=list(shell)
    except ValueError:return
    cwd='.'
    if len(args)>=4 and args[0]=='cd' and args[2]=='&&':cwd=args[1];args=args[3:]
    if not args:return
    if args[:2]==['git','grep']:prog='git grep'; args=args[2:]
    elif args[0] in ('rg','grep'):prog=args[0]; args=args[1:]
    else:return
    limits=[]
    if '|' in args:
        idx=args.index('|');tail=args[idx+1:]
        if not tail or tail[0]!='head':return
        if len(tail)==1:n=10
        elif len(tail)==2 and re.fullmatch(r'-\d+',tail[1]):n=int(tail[1][1:])
        elif len(tail)==3 and tail[1] in ('-n','--lines') and tail[2].isdigit():n=int(tail[2])
        else:return
        limits.append(['stdout_head',n]);args=args[:idx]
    if not args or any(re.fullmatch(r'[&<>;|]+',a) for a in args):return
    if '--files' in args or '--help' in args or '--version' in args:return
    for i,a in enumerate(args):
        if a in ('-m','--max-count') and i+1<len(args) and args[i+1].isdigit():limits.append(['per_file_max_count',int(args[i+1])])
        elif (m:=re.fullmatch(r'(?:-m|--max-count=)(\d+)',a)):limits.append(['per_file_max_count',int(m[1])])
    return {'program':prog,'cwd':cwd,'limits':limits}
def test():
    assert parse("cd /x && rg name a | head -n 3")['limits']==[['stdout_head',3]]
    assert parse("rg -m1 name .")['limits']==[['per_file_max_count',1]]
    assert parse("grep --max-count=2 name .")['limits']==[['per_file_max_count',2]]
    assert parse("git grep 'hello world'")['program']=='git grep'
    assert not parse('rg --files') and not parse('rg name | sort') and not parse('ls') and not parse('rg a && rm x')
    assert parse('rg "(alpha|beta)" .')['limits']==[]
def measure(path):
    start=utc();u='https://huggingface.co/datasets/'+DATA+'/resolve/'+REV+'/'+quote(path)
    raw,errors=fetch(u);result={'path':path,'repo':repo(path),'url':u,'start_utc':start,'end_utc':utc(),'errors':errors}
    if raw is None:return dict(result,status='unavailable')
    doc=json.loads(raw);calls={};events=[];unmatched=0
    for i,msg in enumerate(doc['messages']):
        for c in msg.get('tool_calls') or []:
            if c.get('function',{}).get('name')!='bash':continue
            try:s=json.loads(c['function']['arguments'])['command']
            except (ValueError,KeyError,TypeError):continue
            calls[c['id']]=(i,s)
        if msg.get('role')!='tool' or msg.get('tool_call_id') not in calls:continue
        idx,s=calls.pop(msg['tool_call_id']); parsed=parse(s)
        if parsed:
            e=msg.get('extra') or {};events.append({'message_index':idx,'tool_call_id':msg['tool_call_id'],'command':s,'parse':parsed,'return_code':e.get('returncode')})
        else:unmatched+=1
    seq=[e['command'] for e in events]
    return dict(result,status='ok',sha256=hashlib.sha256(raw).hexdigest(),matched=len(seq),other_bash_with_result=unmatched,
                no_result=len(calls),limited=sum(bool(e['parse']['limits']) for e in events),exact_repeats=len(seq)-len(set(seq)),events=events)
def run():
    rows=json.loads((HERE/'sample.json').read_text())['paths']
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:res=list(pool.map(measure,rows))
    (HERE/'traces.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in res),encoding='utf-8')
    def stat(rr):
        ok=[r for r in rr if r['status']=='ok']
        return {'n':len(rr),'available':len(ok),'with_search':sum(r['matched']>0 for r in ok),'with_limit':sum(r['limited']>0 for r in ok),
                'with_repeat':sum(r['exact_repeats']>0 for r in ok),'search_commands':sum(r['matched'] for r in ok),'limited_commands':sum(r['limited'] for r in ok),
                'repeat_commands':sum(r['exact_repeats'] for r in ok),'other_bash_with_result':sum(r['other_bash_with_result'] for r in ok)}
    save(HERE/'summary.json',{'total':stat(res),'repos':{name:stat([r for r in res if r['repo']==name]) for name in sorted({r['repo'] for r in res})}})
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['select','run','test']);args=a.parse_args()
    test()
    if args.action=='select':select()
    elif args.action=='run':run()

