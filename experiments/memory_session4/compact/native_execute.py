"""Physically replay source-verified exact replacements in original task branch bytes, isolated scratch files."""
import csv,gzip,hashlib,json,os
from pathlib import Path
from collections import defaultdict,Counter
from common import *
from score import intent
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'native'
def accept_source(args,obs):
    p=rel(args.get('path'));ls=printed(obs)
    return p,ls
def verify_blob(code,ls):
    lines=code.replace('\r\n','\n').split('\n')
    return bool(ls) and all(i<=len(lines) and lines[i-1]==text for i,text in ls.items())
def main():
    sources=json.loads((BASE/'sources.json').read_bytes());by_key={(r['inst'],r['path']):r for r in sources}
    records=[];saved=ROOT/'native'/'executed';saved.mkdir(exist_ok=True);cohort=[]
    for k in range(8):
        for row in src(k):
            interested={p:s for (inst,p),s in by_key.items() if inst==row['instance']}
            if not interested:continue
            current={};statuses={}
            for p,r in interested.items():
                if r['status']==200:
                    buf=gzip.decompress((BASE/'blobs'/(r['blob_sha256']+'.gz')).read_bytes());assert hashlib.sha256(buf).hexdigest()==r['blob_sha256']
                    try:current[p]=buf.decode('utf8').replace('\r\n','\n');statuses[p]='branch'
                    except UnicodeError:statuses[p]='non_utf8'
                else:statuses[p]='unavailable_source'
            outcomes={i:intent(row['events'],i) for i in range(4,len(row['events']),4)}
            pending={}
            for i,event in enumerate(row['events']):
                tool,args,obs=event
                if not isinstance(args,dict):continue
                p=rel(args.get('path'));action=args.get('command')
                if i in outcomes and outcomes[i] is not None:
                    path,old,new,accepted,off,_=outcomes[i]
                    if path in interested:pending[i+off-1]=(i,path,old,new,accepted)
                # Actual next replacement can be preceded by other observations after the boundary.
                if i in pending:
                    cut,path,old,new,historical=pending[i];text=current.get(path);unique=text is not None and text.count(old)==1
                    post=text.replace(old,new,1) if unique else None
                    post_printed=printed(obs);observed_match=unique and verify_blob(post,post_printed)
                    physical_sha=None
                    if unique:
                        out=saved/(hashlib.sha256((row['traj']+'|'+str(i)).encode()).hexdigest()+'.txt')
                        with out.open('w+',encoding='utf8',newline='\n') as f:
                            f.write(text);f.seek(0);before=f.read();assert before.count(old)==1
                            f.seek(0);f.write(before.replace(old,new,1));f.truncate();f.flush();f.seek(0);done=f.read();assert done==post
                        physical_sha=hashlib.sha256(out.read_bytes()).hexdigest()
                    records.append({'shard':k,'row':row['row'],'traj':row['traj'],'instance':row['instance'],'cut':cut,'path':path,'tool_time':i,'historically_accepted':historical,'source_state':statuses.get(path),'full_unique':unique,'post_snippet_agrees':bool(observed_match),'printed_lines':len(post_printed),'executed_sha256':physical_sha,'full_bytes':len(text.encode()) if text is not None else None})
                if tool=='bash':
                    # Cannot track shell mutation. Subsequent numbered view rechecks exact observed lines.
                    for q in current:statuses[q]='opaque_since_branch'
                    continue
                if p not in interested:continue
                if action=='view':
                    ls=printed(obs)
                    if p in current and ls:
                        if not verify_blob(current[p],ls):
                            current.pop(p);statuses[p]='diverged_observed_view'
                        else:statuses[p]='observed_agrees'
                elif success(action,p,obs):
                    old=args.get('old_str');new=args.get('new_str','')
                    if p in current and isinstance(old,str) and old and current[p].count(old)==1:
                        current[p]=current[p].replace(old,new,1)
                        ls=printed(obs)
                        if ls and not verify_blob(current[p],ls):current.pop(p);statuses[p]='edit_confirmation_mismatch'
                        else:statuses[p]='replayed_literal_change'
                    else:current.pop(p,None);statuses[p]='unreplayable_prior_edit'
                elif action in ('create','insert','undo_edit'):
                    current.pop(p,None);statuses[p]='unsupported_prior_mutation'
    (BASE/'physical_rows.json').write_text(json.dumps(records,indent=1))
    good={(r['shard'],r['row'],r['cut']) for r in records if r['full_unique'] and r['post_snippet_agrees'] and r['historically_accepted']}
    picked={(r['shard'],r['row'],r['cut']) for r in records}
    statistics=defaultdict(Counter)
    for fn in sorted((ROOT/'scores').glob('*.jsonl.gz')):
        for r in rows(fn):
            key=(r['shard'],r['row'],r['cut'])
            if key not in picked:continue
            for arm,(ph,hit,tok) in r['metrics'].items():
                statistics[arm]['opportunities']+=1
                statistics[arm]['native_validated_opportunities']+=key in good
                statistics[arm]['recovered_and_native_confirmed']+=hit and key in good
                statistics[arm]['historical_excerpt_recovered']+=hit
    result={'sampled_task_files':len(sources),'downloaded_task_files':sum(r['status']==200 for r in sources),'evaluated_future_replacements':len(records),'full_unique':sum(r['full_unique'] for r in records),'confirmed_physical_replacements':len(good),'source_failures':dict(Counter(r['status'] for r in sources)),'state_counts':dict(Counter(r['source_state'] for r in records)),'policies':statistics}
    (BASE/'results.json').write_text(json.dumps(result,indent=1));print({k:v for k,v in result.items() if k!='policies'},flush=True)
if __name__=='__main__':main()
