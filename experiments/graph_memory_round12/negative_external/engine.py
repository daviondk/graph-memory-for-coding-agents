"""Incremental policies receive symmetrical access to two identified revisions in a local Git object store."""
from collections import Counter
import fnmatch, gzip, hashlib, json, re, time
from pathlib import PurePosixPath
from extract import D,get,gz,h,save
from objects import git
from witness import allfiles
def unpack(name):return json.loads(gzip.decompress((D/name).read_bytes()))
def uint(value):return int(value)
def measure(repo,args):
    t=time.perf_counter_ns();p=git(repo,*args,check=False);return p.stdout,p.returncode,time.perf_counter_ns()-t
def hkey(row):return row['iid']+":"+row['tool_call_id']
def where(paths,key):
    p=key['scope']
    if p!="." and p in paths:return 'file'
    if p=="." or any(q.startswith(p+"/") for q in paths):return 'directory'
    return 'absent'
def pathspec(key,ty):
    p=key['scope'];globs=key['globs']
    if ty=='file' or not globs:return [] if p=="." else [":(literal)"+p]
    prefix="" if p=="." else p+"/"
    return [":(glob)"+prefix+"**/"+g for g in globs]
def checked_file_or_directory(key,kind):
    if kind=='absent':return 'absent_scope'
    if kind=='directory' and not key['recurse']:return 'nonrecursive_directory'
    if kind=='file' and key['globs']:return 'explicit_file_with_include'
    return None
def scan(repo,rev,key,ty,full=False):
    args=['grep','-I','-F','-l' if full else '-q']
    if full:args+=['-z']
    if key['oi']:args.append('-i')
    if key['word']:args.append('-w')
    out,rc,ns=measure(repo,args+['-e',key['literal'],rev,'--',*pathspec(key,ty)])
    if rc not in (0,1):raise RuntimeError((repo,rev,key,rc))
    return rc==0,ns,len(out),[n.decode('utf8','surrogateescape').removeprefix(rev+':') for n in out.split(b'\0') if n] if full else []
def hits_line(diff,key):
    lit=re.escape(key['literal'].encode())
    pat=re.compile((b'(?<![A-Za-z0-9_])'+lit+b'(?![A-Za-z0-9_])') if key['word'] else lit, re.ASCII|re.I if key['oi'] else re.ASCII)
    adds=0;hits=0;active=False
    for line in diff.split(b'\n'):
        if line.startswith(b'diff --git '):active=False
        elif line.startswith(b'@@ '):active=True
        elif active and line.startswith(b'+'):
            adds+=1
            if pat.search(line[1:]):hits+=1
    return bool(hits),hits,adds
def counter(repo,old,new,k,ty,arm):
    start=time.perf_counter_ns()
    args=['diff','--no-renames','--no-textconv','--no-ext-diff']
    if arm=='scope':args+=['--name-only','-z']
    elif arm=='exact':args+=['--unified=0','--no-color']
    elif arm=='pickaxe':
        if k['oi'] or k['word']:raise ValueError("native baseline restricted to case-sensitive plain literals")
        pattern=''.join('\\'+c if c in '\\.^$[]()|+*?{}' else c for c in k['literal'])
        args+=['--name-only','-z','-G'+pattern]
    else:raise ValueError(arm)
    out,rc,sub=measure(repo,args+[old,new,'--',*pathspec(k,ty)])
    if rc!=0:raise RuntimeError((repo,arm,k,rc))
    if arm=='exact':hit,num,added=hits_line(out,k)
    else:hit=bool(out);num=added=None
    return {'trigger':hit,'git_output_bytes':len(out),'git_ns':sub,'entire_ns':time.perf_counter_ns()-start,'matching_added_lines':num,'added_lines':added}
def predict():
    lock=get(D/'input.lock.json');assert all(h((D/k).read_bytes())==v for k,v in lock['files'].items())
    keys=unpack('provenance.json.gz');meta={p['iid']:p for p in get(D/'revision_pairs.json')};pred=[];renames={}
    for row in keys:
        r=meta[row['iid']];k=row['key'];repo=row['repo'];a,b=r['parent'],r['merge']
        ty=where(allfiles(repo,a),k)
        if row['iid'] not in renames:
            out=git(repo,'diff','--find-renames','--name-status','-z',a,b).stdout
            fields=out.split(b'\0');i=0;moves=[]
            while i<len(fields) and fields[i]:
                status=fields[i].decode();i+=1
                if status[0] in 'RC':
                    moves.append([status,fields[i].decode(errors='replace'),fields[i+1].decode(errors='replace')]);i+=2
                else:i+=1
            renames[row['iid']]=moves
        reason=checked_file_or_directory(k,ty)
        item={**row,'relation':r['relation'],'old':a,'new':b,'old_scope':ty,'skip_reason':reason,'policies':{}}
        if not reason and r['relation'] in ('direct','earlier_ancestor'):
            item['policies']={m:counter(repo,a,b,k,ty,m) for m in ('scope','exact','pickaxe')}
        pred.append(item)
    gz('forecasts.json.gz',pred);save('rename_receipt.json',renames)
    names=['engine.py','revision_pairs.json','input.lock.json','witness.py','provenance.json.gz','forecasts.json.gz','rename_receipt.json']
    save('forecast.lock.json',{'files':{n:h((D/n).read_bytes()) for n in names}})
    print('decisions sealed',len(pred))
def oracle():
    lock=get(D/'forecast.lock.json');assert all(h((D/k).read_bytes())==v for k,v in lock['files'].items())
    rows=unpack('forecasts.json.gz')
    for r in rows:
        if not r['policies']:continue
        k=r['key'];ty2=where(allfiles(r['repo'],r['new']),k)
        if checked_file_or_directory(k,ty2):
            r['skip_reason']='new_'+checked_file_or_directory(k,ty2);continue
        r['new_scope']=ty2
        z={}
        for stage,ty in [('old',r['old_scope']),('new',ty2)]:
            hit,ns,size,paths=scan(r['repo'],r[stage],k,ty,True)
            z[stage]={'hit':hit,'ms':ns/1e6,'output_bytes':size,'match_count':len(paths),'first_paths':paths[:5]}
        r['oracle']=z
        if z['old']['hit']:r['skip_reason']='old_git_has_match'
    gz('outcomes.json.gz',rows)
    result=Counter((r['relation'],r['support']!='no_prior_root_witness',r.get('skip_reason'),r.get('oracle',{}).get('new',{}).get('hit')) for r in rows)
    print(result)
if __name__=="__main__":
    import sys
    {'predict':predict,'oracle':oracle}[sys.argv[1]]()
