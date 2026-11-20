"""Project literal grep/rg identifiers, never shell syntax, from pinned SWE-smith records."""
import gzip,json,hashlib,re,shlex,itertools,sys
from collections import Counter,defaultdict
from pathlib import Path
from prepare import ROOT,eligible
def digest(x):return hashlib.sha256(x).hexdigest()
def commands(messages):
    for m in messages:
        if m.get('role')!='assistant':continue
        for call in (m.get('tool_calls') or []):
            f=call.get('function',{});a=f.get('arguments',{})
            if isinstance(a,str):
                try:a=json.loads(a)
                except ValueError:continue
            if f.get('name') in ('bash','execute_bash','run_command','terminal') and isinstance(a,dict) and isinstance(a.get('command'),str):yield a['command']
        text=m.get('content','')
        if not isinstance(text,str):text=''.join(z.get('text','') for z in (text or []) if isinstance(z,dict))
        for s in re.findall(r'<function=(?:bash|execute_bash)>(.*?)</function>',text,re.S):
            for cmd in re.findall(r'<parameter=command>(.*?)</parameter>',s,re.S):yield cmd.strip()
def literals(s):
    for segment in re.split(r'&&|\|\||[;|\n]',s):
        try:args=shlex.split(segment.strip())
        except ValueError:continue
        if not args or args[0] not in ('rg','grep'):continue
        i=1
        while i<len(args) and args[i].startswith('-'):
            if args[i] in ('-e','--regexp'):i+=1;break
            i+=2 if args[i] in ('-g','--glob','-t','--type','--include','--exclude','-A','-B','-C','-m') else 1
        if i<len(args) and re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',args[i]) and eligible(args[i]):yield args[i]
def main():
    import pyarrow.parquet as pq
    old=ROOT.parents[1]/'memory_session5/packets';raw=ROOT.parents[1]/'memory_session4/compact/.scratch'
    repos=set(json.loads((ROOT/'source_lock.json').read_bytes()))
    roster={}
    for pattern in ('source/train/*.gz','source/test/*.gz','transfer/source/*.gz','allocation/source/*.gz'):
        for path in old.glob(pattern):
            with gzip.open(path,'rt',encoding='utf-8') as f:
                for line in f:
                    o=json.loads(line);repo=o['instance'].partition('.')[0].replace('__','/').lower()
                    if repo in repos:roster[o['shard'],o['row']]=(repo,o['messages_sha'],o['instance'])
    seen=Counter();hist=Counter();allkeys=defaultdict(list);items=json.loads((old/'shards.json').read_bytes())
    for k,j in enumerate(items):
        path=raw/Path(j['path']).name; pos=0
        with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==j['lfs']['oid']
        pf=pq.ParquetFile(path)
        for b in pf.iter_batches(batch_size=32,columns=['messages']):
            for i in range(b.num_rows):
                if (k,pos+i) not in roster:continue
                repo,sha,iid=roster[k,pos+i];v=b[0][i].as_py()
                assert digest(v.encode())==sha
                seen[repo]+=1
                for n,s in enumerate(commands(json.loads(v))):
                    hist[repo]+=1
                    for word in literals(s):
                        allkeys[repo].append({'word':word,'traj_hash':sha,'event':n,'shard':k,'row':pos+i,'issue':iid})
            pos+=b.num_rows
        pf.close()
    (ROOT/'real_intents.json').write_text(json.dumps({'source':'https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories/tree/08e109b4a59eaeebf80e4675cd125d42e7ac99a4','shards':[{a:j[a] for a in ('path','lfs')} for j in items],'vetted':dict(seen),'shell_calls':dict(hist),'queries':allkeys},indent=1))
    print('queries by repository',[(r,len(v),len({z['word'] for z in v})) for r,v in allkeys.items()])
if __name__=='__main__':main()
