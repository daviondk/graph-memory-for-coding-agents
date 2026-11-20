"""Grade sealed prefix memories against the first next concrete historical replacement; no generation here."""
import csv,gzip,hashlib,json,re,sys,tempfile
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from common import *
def intent(events,start):
    for j,(tool,a,feedback) in enumerate(events[start:start+4],1):
        if not isinstance(a,dict):continue
        if tool not in ('str_replace_editor','str_replace_based_edit_tool','edit_file') or a.get('command')!='str_replace':continue
        p,old,new=rel(a.get('path')),a.get('old_str'),a.get('new_str','')
        if p and isinstance(old,str) and old and isinstance(new,str):
            return p,old,new,success('str_replace',p,feedback),j,feedback[:180]
    return None
def matching(items,indices,path,old):
    lines={}
    for i in indices:
        p,n,e,_,body=items[i]
        if p!=path:continue
        ss=body.split('\n');assert len(ss)==e-n+1
        for j,s in enumerate(ss,n):lines[j]=s
    hits=[]
    for ns in groups(lines):
        body='\n'.join(lines[n] for n in ns)
        pos=body.find(old)
        if pos>=0:
            if body.find(old,pos+1)>=0:return None
            hits.append(body)
    return hits[0] if len(hits)==1 else None
def physical(body,old,new):
    pre=body.encode();a=old.encode();b=new.encode()
    with tempfile.TemporaryFile(dir=ROOT/'scratch_exec') as f:
        f.write(pre);f.seek(0);actual=f.read();idx=actual.index(a);assert actual.find(a,idx+1)<0
        expected=actual[:idx]+b+actual[idx+len(a):]
        f.seek(0);f.write(actual.replace(a,b,1));f.truncate();f.flush();f.seek(0)
        proof=f.read();assert proof==expected and len(proof)==len(actual)-len(a)+len(b)
    return [hashlib.sha256(pre).hexdigest(),hashlib.sha256(proof).hexdigest()]
def update_full(cache,event):
    tool,a,text=event
    if tool=='bash':
        # An arbitrary shell call can mutate a file. Clear the independently certified whole-file state.
        cache.clear();return
    if not isinstance(a,dict) or tool not in ('str_replace_editor','str_replace_based_edit_tool','edit_file'):return
    p=rel(a.get('path'));action=a.get('command')
    if action!='view':
        cache.pop(p,None);return
    if a.get('view_range') not in (None,[],[1,-1]):return
    ls=printed(text);observed=list(ls)
    if not ls or observed!=list(range(1,len(ls)+1)) or any(s in text.lower() for s in ('<response clipped>','<response clipped','output truncated','... truncated','characters have been omitted','[... omitted')):return
    # Keep only strict cat -n records, with no diagnostic/truncation between or after lines.
    norm=text.replace('\r\n','\n').split('\n');i=next((k for k,v in enumerate(norm) if LINE.fullmatch(v)),len(norm))
    if any(not LINE.fullmatch(v) for v in norm[i:] if v):return
    cache[p]='\n'.join(ls[n] for n in observed)
def one(k):
    inp=iter(rows(ROOT/'sealed'/f'{k}.jsonl.gz'));counts=Counter();reports=[];statistics=[];repo_seen={}
    for row in src(k):
        states={m:{} for m in ('drop','rebase','stale')};meta=newmeta();full={};events=row['events'];inst=row['instance'];counts['sessions']+=1
        for t,ev in enumerate(events,1):
            advance(states,meta,ev,t);update_full(full,ev)
            if t%4 or t==len(events):continue
            rr,tt,preds,layout=next(inp);assert (rr,tt)==(row['row'],t);counts['boundaries']+=1
            goal=intent(events,t)
            if not goal:continue
            path,old,new,accepted,offset,feedback=goal
            seen={m:pages(z) for m,z in states.items()};assert all(hashlib.sha256(emit(v).encode()).hexdigest()==layout[m] for m,v in seen.items())
            counts['intents']+=1;counts['accepted']+=accepted
            strip=path in full;certified=strip and full[path].count(old)==1;proof={}
            if accepted and certified:proof['whole_file']=physical(full[path],old,new)
            ceiling={}
            for m,it in seen.items():ceiling[m]=matching(it,range(len(it)),path,old) is not None
            metrics={}
            for key,(indices,tok) in preds.items():
                arm,b=key.split(':');assert tok<=int(b);m=arm.split('_')[0] if '_' in arm and arm!='one_reopen' else 'rebase'
                if arm=='paths':ph=path in indices;body=None
                else:
                    it=seen[m];ph=any(it[i][0]==path for i in indices);body=matching(it,indices,path,old)
                hit=body is not None
                if hit:
                    h=hashlib.sha256(body.encode()).hexdigest()
                    if h not in proof:proof[h]=physical(body,old,new)
                metrics[key]=[int(ph),int(hit),tok]
            previous=meta['paths'].get(path,-1)
            out={'instance':inst,'traj':row['traj'],'model':row['model'],'shard':k,'row':row['row'],'cut':t,'offset':offset,'path':path,'old_sha':hashlib.sha256(old.encode()).hexdigest(),'old_bytes':len(old.encode()),'old_lines':old.count('\n')+1,'new_sha':hashlib.sha256(new.encode()).hexdigest(),'accepted':accepted,'edited_before':path in meta['edited'],'steps_since_view':(t-previous if previous>=0 else None),'opaque_since':meta['bash_t']>previous or any(e[0]=='bash' for e in events[t:t+offset-1]),'known_whole_at_boundary':strip,'whole_hit':certified,'ceiling':ceiling,'metrics':metrics,'physical':proof}
            reports.append(out)
    assert next(inp,None) is None
    fn=ROOT/'scores'/f'{k}.jsonl.gz'
    with gzip.open(fn,'wt',encoding='utf8') as f:
        for r in reports:print(emit(r),file=f)
    print(k,dict(counts),flush=True);return counts
def main():
    locked=json.loads((ROOT/'prediction_lock.json').read_bytes())['files']
    assert all(digest(ROOT/n)==v for n,v in locked.items())
    (ROOT/'scratch_exec').mkdir(exist_ok=True);(ROOT/'scores').mkdir(exist_ok=True)
    with ProcessPoolExecutor(3) as pool:c=sum(pool.map(one,range(8)),Counter())
    (ROOT/'counts.json').write_text(json.dumps(c,indent=1))
if __name__=='__main__':main()
