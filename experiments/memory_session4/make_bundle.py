"""Package reproducible projections and run receipts. Original raw downloads remain on D."""
from pathlib import Path
import hashlib,json,os,zipfile
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'outputs'
SKIP_ACTION={'restarted_builds.bson.gz','restarted_jobs.bson.gz','restarted_logs.prefix.gz.part','restarted_logs.tail128.gz.part'}

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for buf in iter(lambda:f.read(1024*1024),b''):h.update(buf)
    return h.hexdigest()

def include(p):
    rel=p.relative_to(ROOT)
    if not p.is_file() or any(s in ('.git','__pycache__','.scratch','raw') for s in rel.parts):return False
    if p.suffix.lower() in ('.pyc','.tmp','.part'):return False
    if rel.parts[0]=='action' and rel.name in SKIP_ACTION:return False
    if rel.parts[0]=='report' and len(rel.parts)>2 and rel.parts[1] in ('temp','final','preview','qa','render'):
        return rel.parts[1]=='final' and rel.name in ('qa.json','published.json')
    return rel.name!='MANIFEST.sha256.json'

def main():
    items={p.relative_to(ROOT).as_posix():p for p in ROOT.rglob('*') if include(p)}
    for suffix in ('docx','pdf'):
        name='agent-memory-session4-results.'+suffix
        items['delivered/'+name]=OUT/name
    manifest={n:sha(f) for n,f in sorted(items.items())}
    target=OUT/'agent-memory-session4-records.zip';temp=target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for name,f in sorted(items.items()):
            z.write(f,name,compress_type=zipfile.ZIP_STORED if f.suffix in ('.gz','.zip','.pdf','.docx','.png') else zipfile.ZIP_DEFLATED)
        z.writestr('MANIFEST.sha256.json',json.dumps(manifest,indent=1)+'\n')
    with zipfile.ZipFile(temp) as z:
        assert z.testzip() is None and len(z.infolist())==len(manifest)+1
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    os.replace(temp,target)
    print(target,len(items),'files',target.stat().st_size,'bytes',sha(target))
if __name__=='__main__':main()
