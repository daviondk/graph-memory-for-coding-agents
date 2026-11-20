from pathlib import Path
import collections,gzip,hashlib,json,re,sys
from intents import literals
from prepare import ROOT,emit,eligible,key
def txt(m):
    x=m.get('content')
    return x if isinstance(x,str) else '\n'.join(y.get('text','') for y in x or [] if isinstance(y,dict))
def events(ms):
    if any(m.get('role')=='tool' for m in ms):
        calls={}
        for m in ms:
            if m.get('role')=='assistant':
                for c in m.get('tool_calls') or []:
                    f=c.get('function',{});a=f.get('arguments') or {}
                    if isinstance(a,str):
                        try:a=json.loads(a)
                        except ValueError:continue
                    calls[c.get('id')]=(f.get('name'),a)
            elif m.get('role')=='tool':
                cid=m.get('tool_call_ids') or [m.get('tool_call_id')]
                if len(cid)==1 and cid[0] in calls:yield (*calls.pop(cid[0]),txt(m))
    else:
        last=None
        for m in ms:
            if m.get('role')=='assistant':
                fs=re.findall(r'<function=([\w.-]+)>(.*?)</function>',txt(m),re.S)
                last=None
                if len(fs)==1:
                    name,fields=fs[0];last=(name,{k:v.strip('\n') for k,v in re.findall(r'<parameter=([\w.-]+)>(.*?)</parameter>',fields,re.S)})
            elif m.get('role')=='user' and last:
                yield (*last,txt(m));last=None
def project():
    import pyarrow.parquet as pq
    old=ROOT.parents[1]/'memory_session5/packets';raw=ROOT.parents[1]/'memory_session4/compact/.scratch';roster={}
    for pattern in ('source/train/*.gz','source/test/*.gz','transfer/source/*.gz','allocation/source/*.gz'):
        for path in old.glob(pattern):
            for l in gzip.open(path,'rt',encoding='utf8'):
                r=json.loads(l);roster[r['shard'],r['row']]=(r['instance'],r['messages_sha'])
    output=[]
    for k,j in enumerate(json.loads((old/'shards.json').read_bytes())):
        path=raw/Path(j['path']).name
        with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==j['lfs']['oid']
        pf=pq.ParquetFile(path);offset=0
        for batch in pf.iter_batches(batch_size=32,columns=['messages']):
            for i in range(batch.num_rows):
                if (k,offset+i) not in roster:continue
                iid,sha=roster[k,offset+i];s=batch[0][i].as_py();assert hashlib.sha256(s.encode()).hexdigest()==sha
                trace=[];edits=0;bash=0
                for tick,(name,arg,feedback) in enumerate(events(json.loads(s))):
                    if not isinstance(arg,dict):continue
                    if name in ('str_replace_editor','str_replace_based_edit_tool','edit_file') and arg.get('command')=='str_replace' and re.search(r'(?:The file .*? has been edited\.|successfully replaced)',feedback[:1300],re.I):edits+=1
                    if name not in ('bash','execute_bash','run_command','terminal') or not isinstance(arg.get('command'),str):continue
                    bash+=1;cmd=arg['command'];ts=sorted(set(literals(cmd)))
                    if ts:trace.append([tick,edits,hashlib.sha256(cmd.encode()).hexdigest(),[key(t) for t in ts]])
                output.append({'issue':iid,'repo':iid.partition('.')[0],'shard':k,'row':offset+i,'messages_sha':sha,'shell_calls':bash,'edits':edits,'literal_calls':trace})
            offset+=batch.num_rows
        pf.close()
    (ROOT/'exposure.jsonl.gz').write_bytes(gzip.compress(('\n'.join(map(emit,output))+'\n').encode(),mtime=0))
def compute():
    counts=collections.Counter();repos=collections.defaultdict(collections.Counter)
    for l in gzip.open(ROOT/'exposure.jsonl.gz','rt'):
        r=json.loads(l);c=collections.Counter();c['trajectories']=1;c['shell_calls']=r['shell_calls'];c['confirmed_edits']=r['edits']
        c['with_any_literal']=int(bool(r['literal_calls']));lastt={};lastcmd={}
        for tick,nedit,cmd,terms in r['literal_calls']:
            c['literal_calls']+=1;prev=[lastt[t] for t in terms if t in lastt]
            if prev:c['repeat_identifier']+=1
            if any(nedit>a for a in prev):c['repeat_id_after_edit']+=1
            if cmd in lastcmd:c['repeat_exact_shell']+=1
            if cmd in lastcmd and nedit>lastcmd[cmd]:c['repeat_exact_after_edit']+=1
            for t in terms:lastt[t]=nedit
            lastcmd[cmd]=nedit
        for k in ('repeat_identifier','repeat_id_after_edit','repeat_exact_after_edit'):c['tasks_'+k]=int(c[k]>0)
        counts.update(c);repos[r['repo']].update(c)
    return {'all':dict(counts),'by_repo':{k:dict(v) for k,v in repos.items()}}
if __name__=='__main__':
    if '--project' in sys.argv:project()
    out=compute();p=ROOT/'exposure_results.json'
    if '--verify' in sys.argv:assert out==json.loads(p.read_bytes())
    else:p.write_text(json.dumps(out,indent=2))
    print(out['all'])
