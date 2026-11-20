"""Run frozen, independent model requests with the user's existing Codex CLI session.

Usage: python run_model.py requests.jsonl run_dir [--workers 2]
One isolated temporary working directory per call, no parent transcript or prior turns.
The supplied prompts are the complete experimental input. Never read user credentials.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

MODEL = 'gpt-6.1-sol'
PREFIX = ('You are a decision maker in a controlled experiment. Use only the information supplied below. '
          'Do not use any tools, workspace files, web, or other agents. Output exactly the JSON requested, '
          'without commentary or markdown.\n\n')
def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()
def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def invoke(request,dest,cli,version):
    key=request['id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',key):
        raise ValueError(f'Invalid request ID {key!r}')
    report=dest/(key+'.json')
    prompt=PREFIX+request['prompt']
    digest=hashlib.sha256(prompt.encode()).hexdigest()
    if report.exists():
        old=json.loads(report.read_text(encoding='utf-8'))
        if old['prompt_sha256']!=digest: raise ValueError('Request changed: '+key)
        return (key,old['status'])
    history=[]
    for attempt in range(1,3):
        with tempfile.TemporaryDirectory(prefix='memory-study-') as tmp:
            cmd=[cli,'exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check',
                 '-s','read-only','-m',MODEL,'-c','model_reasoning_effort="low"','--json','--color','never','-']
            start=now(); t0=time.monotonic()
            try:
                run=subprocess.run(cmd,input=prompt.encode('utf-8'),cwd=tmp,stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,timeout=135,check=False)
                out=run.stdout.decode('utf-8','replace');err=run.stderr.decode('utf-8','replace');code=run.returncode
            except subprocess.TimeoutExpired as e:
                out=(e.stdout or b'').decode('utf-8','replace');err=(e.stderr or b'').decode('utf-8','replace');code=124
            events=[]
            for line in out.splitlines():
                try:events.append(json.loads(line))
                except ValueError:events.append({'type':'unparsed_output','text':line})
            messages=[e.get('item',{}).get('text','') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
            actions=[e.get('item',{}).get('type') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') not in ['agent_message','reasoning']]
            usage=next((e.get('usage',{}) for e in reversed(events) if e.get('type')=='turn.completed'),{})
            status='ok' if not code and messages and not actions else ('tool_violation' if actions else 'infrastructure_error')
            record={'attempt':attempt,'started_utc':start,'ended_utc':now(),'elapsed_s':round(time.monotonic()-t0,4),
                    'returncode':code,'status':status,'actions':actions,'usage':usage,'stderr':err,'events':events}
            history.append(record)
            if status!='infrastructure_error':break
    result={'id':key,'model':MODEL,'reasoning_effort':'low','cli_version':version,'protocol_version':1,
            'command':cmd[1:],'prompt':prompt,'prompt_sha256':digest,'status':status,'text':messages[-1] if messages else '',
            'usage':usage,'attempts':history}
    temp=report.with_suffix('.partial');dump(temp,result);temp.replace(report)
    return (key,status)
def main():
    a=argparse.ArgumentParser();a.add_argument('requests',type=Path);a.add_argument('destination',type=Path);a.add_argument('--workers',type=int,default=2)
    ns=a.parse_args(); ns.destination.mkdir(parents=True,exist_ok=True)
    rows=[json.loads(l) for l in ns.requests.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
    assert len({r['id'] for r in rows})==len(rows)
    cli=shutil.which('codex');version=subprocess.check_output([cli,'--version'],text=True).strip()
    with concurrent.futures.ThreadPoolExecutor(max_workers=ns.workers) as pool:
        futs=[pool.submit(invoke,r,ns.destination,cli,version) for r in rows]
        for f in concurrent.futures.as_completed(futs):
            k,s=f.result();print(k,s,flush=True)
if __name__=='__main__':main()

