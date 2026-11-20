"""Build and verify a portable research archive, keeping the original workspace intact."""
from pathlib import Path
import hashlib,json,os,zipfile
ROOT=Path(__file__).resolve().parent;OUT=ROOT.parents[1]/'outputs'
def sha(p):
    with p.open('rb') as fp:
        h=hashlib.sha256()
        for buf in iter(lambda:fp.read(1024*1024),b''):h.update(buf)
        return h.hexdigest()
def include(p):
    rel=p.relative_to(ROOT)
    if not p.is_file() or any(i in ('.git','__pycache__') for i in rel.parts) or p.suffix.lower() in ('.pyc','.tmp'):return False
    if rel.parts[0]=='report' and len(rel.parts)>2 and rel.parts[1] in ('temp','final','preview','render','qa'):
        return rel.parts[1]=='final' and rel.name in ('qa.json','published.json')
    return rel.name not in ('MANIFEST.sha256.json',)
def main():
    items={p.relative_to(ROOT).as_posix():p for p in ROOT.rglob('*') if include(p)}
    for suffix in ('pdf','docx'):
        name='agent-memory-session3-results.'+suffix;items['delivered/'+name]=OUT/name
    digests={n:sha(p) for n,p in sorted(items.items())}
    path=OUT/'agent-memory-session3-records.zip';tmp=path.with_suffix('.zip.tmp')
    already={'.gz','.zip','.pdf','.docx','.whl','.png','.jpg'}
    with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for n,p in sorted(items.items()):z.write(p,n,compress_type=zipfile.ZIP_STORED if p.suffix.lower() in already else zipfile.ZIP_DEFLATED)
        z.writestr('MANIFEST.sha256.json',json.dumps(digests,indent=1)+'\n')
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None and len(z.infolist())==len(digests)+1
        for n,h in digests.items():
            with z.open(n) as f:
                check=hashlib.sha256()
                for b in iter(lambda:f.read(1024*1024),b''):check.update(b)
                assert h==check.hexdigest(),n
    os.replace(tmp,path)
    print(path, len(digests),'files',path.stat().st_size,'bytes',sha(path))
if __name__=='__main__':main()
