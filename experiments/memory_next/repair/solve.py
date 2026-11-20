"""Local tool-using solver. No test patches, graded outcomes or relationship labels imported."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import time
import uuid
import requests
from workspace import HERE,create,shell,patch,docker

ENDPOINT='http://127.0.0.1:18839/replicate/0/v1/chat/completions'
MODEL='qwen38-27b-ud-q4km'
TOOLS=[]
for name,desc,params,req in [
    ('bash','Run a local bash command or Python here-document in the repository. Output may be shortened. No network.',{'command':{'type':'string'}},['command']),
    ('read_details','Request the preserved list of evidence from the earlier edit when available.',{},[])]:
    TOOLS.append({'type':'function','function':{'name':name,'description':desc,'parameters':{'type':'object','properties':params,'required':req,'additionalProperties':False}}})
SYSTEM=('Fix the current issue by editing the repository in /testbed. Use bash to inspect files, edit them, and run relevant tests. '
        'The container is offline. Each command starts in /testbed. You have up to 24 model turns. On completion, leave the working-tree changes in place and answer briefly. '
        'An earlier experience may help, but its explanation is historical and may be wrong or irrelevant. Check claims against this checkout. '
        'When offered, read_details returns additional prior edit evidence. Do not use git history or look for benchmark materials.')
def load(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=1),encoding='utf8');tmp.replace(p)
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def clipped(s,n=6000):
    return s if len(s)<=n else s[:n*2//3]+'\n[part omitted]\n'+s[-n//3:]
def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def log(j,v):
    with j.open('a',encoding='utf8') as f:f.write(json.dumps(v,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def note(s,arm):
    if not s:return 'No eligible earlier record; read_details is unavailable.'
    intro='Previous issue: '+s['symptom']+'\nPrior public explanation: '+s['closure']+'\n'
    if arm=='eager':return intro+'Prior edit evidence: '+s['edits']+'\nThe same evidence has already been shown.'
    if arm=='on_demand':return intro+'Additional prior edit evidence is available once via read_details.'
    return intro+'Additional prior edit evidence is unavailable.'
def run(r,arm,record,proof):
    folder=HERE/'runs'/r['id']/arm
    if (folder/'complete.json').exists():return
    if folder.exists():
        old=HERE/'interrupted'/r['id']/arm/str(int(time.time()));old.parent.mkdir(exist_ok=True,parents=True);folder.rename(old)
    folder.mkdir(exist_ok=True,parents=True)
    cid=create(r,proof);seen=arm=='eager' and bool(record);reads=0;offered=bool(record) and arm=='on_demand'
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':'Current issue:\n'+r['question']+'\n\nMemory:\n'+note(record,arm)}]
    totals=[0,0];start=time.time();reason='call_limit';accepted=0
    try:
        for turn in range(24):
            forwarded=[m.copy() for m in messages]
            # Keep an upper margin for the native 49,152-token window on long tool responses.
            if sum(len(json.dumps(m,ensure_ascii=False)) for m in forwarded)>100000:
                for m in forwarded[2:-2]:
                    if m['role']=='tool':m['content']=clipped(m['content'],600)
            seed=int(sha('repair-v1|'+r['id']+'|'+str(turn))[:8],16)%(2**31-1)
            payload={'model':MODEL,'messages':forwarded,'tools':TOOLS,'temperature':.5,'top_p':.95,'seed':seed,'max_tokens':768,'stream':False}
            save(folder/f'prompt-{turn+1:02}.json',payload)
            response=requests.post(ENDPOINT,json=payload,timeout=650)
            if not response.ok:raise RuntimeError(f'{response.status_code}: {response.text[:500]}')
            out=response.json();save(folder/f'response-{turn+1:02}.json',out)
            u=out['usage'];accepted+=1;totals[0]+=u['prompt_tokens'];totals[1]+=u['completion_tokens']
            msg=out['choices'][0]['message'];assistant={'role':'assistant','content':msg.get('content') or ''}
            tc=msg.get('tool_calls') or []
            if tc:assistant['tool_calls']=tc
            messages.append(assistant)
            if not tc:reason='final_message';break
            for k,c in enumerate(tc):
                fn=c.get('function',{});name=fn.get('name');orig=fn.get('arguments','{}');started=time.time();err=None
                try:
                    args=json.loads(orig) if isinstance(orig,str) else orig
                    if name=='bash':
                        proc=shell(cid,args['command'])
                        stdout=proc.stdout.decode('utf8','replace');stderr=proc.stderr.decode('utf8','replace')
                        text='Exit '+str(proc.returncode)+'\n'+clipped(stdout+('\n'+stderr if stderr else ''))
                    elif name=='read_details':
                        reads+=1;stdout=stderr=''
                        if offered and not seen:text=record['edits'];seen=True
                        elif seen:text='Already present earlier in this session.'
                        else:text='Details unavailable for this session.'
                    else:text='Unknown tool.';stdout=stderr=''
                except (ValueError,KeyError,TypeError) as exc:
                    stdout=stderr='';text='Invalid tool arguments';err=str(exc)
                log(folder/'actions.jsonl',{'turn':turn+1,'index':k,'name':name,'arguments':orig,'seconds':time.time()-started,'stdout':stdout,'stderr':stderr,'context_output':text,'error':err})
                messages.append({'role':'tool','tool_call_id':c['id'],'content':text})
        diff=patch(cid)
        (folder/'candidate.patch').write_bytes(diff)
        save(folder/'complete.json',{'id':r['id'],'arm':arm,'record_available':bool(record),'record_key':record['key'] if record else None,'calls':accepted,'input_tokens':totals[0],'output_tokens':totals[1],'read_requests':reads,'evidence_shown':seen,'elapsed_s':time.time()-start,'finished':stamp(),'finish_reason':reason,'patch_bytes':len(diff),'patch_sha256':hashlib.sha256(diff).hexdigest(),'container':cid})
        print(r['id'],arm,accepted,len(diff),flush=True)
    finally:docker(['rm','-f',cid],check=False)

if __name__=='__main__':
    # safe_cards.json is created only from temporal admissions, without target labels or tests.
    rows={r['id']:r for r in load(HERE/'public_tasks.json')}
    cards=load(HERE/'safe_cards.json');proofs=load(HERE/'images.json')
    for iid,arm in load(HERE/'assignments.json'):
        run(rows[iid],arm,cards[iid],proofs[iid])

