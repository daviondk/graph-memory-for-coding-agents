"""Independent byte-level oracle for all accepted or rejected prior observations on both revisions."""
import collections,hashlib,json,subprocess,tempfile
from pathlib import Path
from witness import allfiles
from engine import unpack,hkey
from batch import applies,pat
from extract import D,get,gz,save
from objects import ENV,local,CACHE
def one_repo(repo,rows):
    qmap={};requirements=collections.defaultdict(set);volume=0
    for r in rows:
        if not r.get('oracle'):continue
        for st in ('old','new'):
            idx=(hkey(r),st);qmap[idx]={'ids':[],'k':r['key'],'oracle':r['oracle'][st]['hit'],'files':0,'hit_files':0,'bytes':0}
            q=qmap[idx];files=allfiles(repo,r[st])
            for p,oid in files.items():
                if applies(p,r['key']):requirements[oid].add(idx);q['ids'].append(oid);q['files']+=1
    if not qmap:return {},{}
    ids=sorted(requirements);pats={i:pat(q['k']) for i,q in qmap.items()}
    by_blob={};hits=collections.defaultdict(set)
    with tempfile.TemporaryFile(dir=CACHE) as inp:
        inp.write(('\n'.join(ids)+'\n').encode());inp.seek(0)
        process=subprocess.Popen(['git','-C',str(local(repo)),'cat-file','--batch'],stdin=inp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV)
        for oid in ids:
            hdr=process.stdout.readline().split();assert hdr[:2]==[oid.encode(),b'blob']
            size=int(hdr[2]);payload=process.stdout.read(size);assert process.stdout.read(1)==b'\n';by_blob[oid]=size;volume+=size
            if b'\0' in payload[:8000]:continue
            for idx in requirements[oid]:
                if pats[idx].search(payload):hits[idx].add(oid)
        assert process.wait(timeout=30)==0
    result={}
    for (key,st),q in qmap.items():
        q['bytes']=sum(by_blob[oid] for oid in q['ids']);q['hit_files']=sum(oid in hits[key,st] for oid in q['ids'])
        q['agrees']=bool(q['hit_files'])==q['oracle']
        result.setdefault(key,{})[st]={k:q[k] for k in ('bytes','files','hit_files','agrees')}
    return result,{'unique_blobs':len(ids),'raw_unique_blob_bytes':volume}
if __name__=='__main__':
    rows=unpack('outcomes.json.gz');result={};costs={}
    for repo in sorted(set(r['repo'] for r in rows)):
        partial,desc=one_repo(repo,[r for r in rows if r['repo']==repo]);result.update(partial);costs[repo]=desc
    gz('independent_blob_checks.json.gz',result)
    mismatches=[(k,stage) for k,v in result.items() for stage,e in v.items() if not e['agrees']]
    save('blob_validation.json',{'repos':costs,'checks':2*len(result),'mismatches':mismatches,'sum_unique_read_bytes':sum(v['raw_unique_blob_bytes'] for v in costs.values())})
    print('checked',2*len(result),'mismatches',mismatches[:6])
