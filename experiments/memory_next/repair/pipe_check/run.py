"""Replay all commands through the unmodified checkout and shell functions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
import workspace
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def save(path,x):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(x,ensure_ascii=False,indent=1)+'\n',encoding='utf8');tmp.replace(path)
def stamp():return datetime.now(timezone.utc).isoformat()
def load_rows():return read(ROOT/'action_audit.json')['tests']

def split_unquoted(source,sep):
    parts=[];last=0;quote=None;escaped=False
    for i,char in enumerate(source):
        if escaped:escaped=False;continue
        if char=='\\' and quote!="'":escaped=True;continue
        if quote:
            if char==quote:quote=None
            continue
        if char in ('"',"'"):quote=char;continue
        if char==sep:parts.append(source[last:i]);last=i+1
    assert quote is None and not escaped
    return parts+[source[last:]]

def register():
    rec={'utc':stamp(),'counts':{'actions':312,'commands':20},'files':{n:sha(p) for n,p in
         [('protocol',HERE/'PROTOCOL.md'),('replay',HERE/'run.py'),('primary_audit',ROOT/'action_audit.json'),
          ('primary_regex',ROOT/'action_audit.py'),('workspace',ROOT/'workspace.py'),('images',ROOT/'images.json')]}}
    path=HERE/'registration.json'
    if path.is_file():assert read(path)['files']==rec['files']
    else:save(path,rec)
    print('Registered',len(load_rows()),'command rows',flush=True)

def stages(segment):
    blocks=split_unquoted(segment,'|')
    assert re.match(r'^\s*(?:cd /testbed && )?python -m pytest ',blocks[0]),blocks[0]
    return ['pytest']+[shlex.split(s)[0] for s in blocks[1:]]

def instrument(command):
    setup=r'''
pipe_audit=/tmp/monitor-test-status
mkdir -p "$pipe_audit"
python() {
    if [ "$1" = -m ] && [ "$2" = pytest ]; then
        command python "$@"
        local native=$?
        printf '%s\n' "$native" >> "$pipe_audit/pytest"
        return "$native"
    fi
    command python "$@"
}
capture_pipe() {
    local step="$1" outer="$2"
    shift 2
    printf '%s\t%s\t%s\n' "$step" "$outer" "$*" >> "$pipe_audit/pipeline"
    return "$outer"
}
'''
    body=[];info=[]
    for i,segment in enumerate(split_unquoted(command,';')):
        body.append(segment.strip())
        if 'python -m pytest ' in segment:
            parts=stages(segment)
            body.append('capture_pipe '+str(i)+' "$?" "$'+'{PIPESTATUS[@]}"')
            argv=shlex.split(split_unquoted(segment,'|')[0].replace('cd /testbed && ','',1).strip())
            assert argv[-1]=='2>&1'
            info.append({'segment':i,'stages':parts,'args':argv[:-1],'collect_only':'--collect-only' in argv})
    assert info
    return setup+'\n'+'; '.join(body),info

def sandbox(iid):
    source=next(x for x in read(ROOT/'public_tasks.json') if x['id']==iid)
    return workspace.create(source,read(ROOT/'images.json')[iid])

def execute(folder,iid,command,sidecars=False):
    folder.mkdir(exist_ok=True,parents=True)
    cid=sandbox(iid)
    start=stamp();begin=time.monotonic()
    try:
        p=workspace.shell(cid,command)
        (folder/'stdout.bin').write_bytes(p.stdout);(folder/'stderr.bin').write_bytes(p.stderr)
        if sidecars:
            for name in ('pipeline','pytest'):
                c=workspace.shell(cid,'cat /tmp/monitor-test-status/'+name)
                (folder/(name+'.tsv')).write_bytes(c.stdout)
        result={'utc_begin':start,'elapsed_s':round(time.monotonic()-begin,3),'native_shell_returncode':p.returncode,
                'cid':cid,'stdout_bytes':len(p.stdout),'stderr_bytes':len(p.stderr),'stdout_sha256':sha(folder/'stdout.bin'),'stderr_sha256':sha(folder/'stderr.bin')}
        save(folder/'run.json',result)
        return result
    finally:workspace.docker(['rm','-f',cid])

def pair(item):
    idx,row=item
    path=HERE/'raw'/f'{idx+1:02d}';path.mkdir(exist_ok=True,parents=True)
    if (path/'complete.json').exists():return
    cmd=row['command'];body,info=instrument(cmd)
    (path/'original.sh').write_text(cmd+'\n',encoding='utf8')
    (path/'instrumented.sh').write_text(body+'\n',encoding='utf8')
    save(path/'design.json',{'index':idx+1,**row,'pipelines':info})
    original=execute(path/'untouched',row['id'],cmd)
    instrumented=execute(path/'instrumented',row['id'],body,True)
    inner=(path/'instrumented'/'pytest.tsv').read_text().splitlines()
    sig_count=0
    for j,(rc,desc) in enumerate(zip(inner,info)):
        if int(rc)==141:
            execute(path/f'direct-{j+1:02d}',row['id'],shlex.join(desc['args']))
            sig_count+=1
    save(path/'complete.json',{'when':stamp(),'direct_probes':sig_count,'untouched_rc':original['native_shell_returncode'],'hooked_rc':instrumented['native_shell_returncode']})
    print(idx+1,row['id'],row['arm'],'completed',flush=True)

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('command',choices=('register','run'));args=cli.parse_args()
    if args.command=='register':register()
    else:
        assert (HERE/'registration.json').is_file()
        register()
        with ThreadPoolExecutor(max_workers=2) as th:list(th.map(pair,enumerate(load_rows())))

