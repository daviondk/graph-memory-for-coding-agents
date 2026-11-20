"""Build an immutable portable result snapshot without the model weights or cached code excerpts."""
from pathlib import Path
import hashlib,json,os,sys,zipfile
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent.parent/'outputs'
OMIT={'__pycache__','.git','weights'}
SKIP_NAMES={'dense_texts.jsonl.gz','fixed_queries.jsonl.gz'}
def include(p):
    rel=p.relative_to(ROOT);name=rel.as_posix()
    if not p.is_file() or any(x in OMIT for x in rel.parts):return False
    if p.name in SKIP_NAMES or p.suffix in {'.pyc','.tmp','.pid','.partial'}:return False
    if name.startswith('serbench/upstream/data/') and p.name=='items.jsonl.gz':return False
    if name.startswith('report/') and len(rel.parts)>2:
        return name in {'report/final/qa.json','report/final/published.json','report/final/agent-memory-session5-results.docx','report/final/agent-memory-session5-results.pdf'}
    if name.startswith('report/') and p.suffix not in {'.py','.png','.pdf'}:return False
    if name in {'live/runtime/pid.txt','live/runtime/monitor.pid'}:return False
    return True
def main():
    target=OUT/'agent-memory-session5-records.zip'
    tmp=target.with_suffix('.tmp')
    files=sorted(p for p in ROOT.rglob('*') if include(p))
    manifest={}
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for p in files:
            key=p.relative_to(ROOT).as_posix();data=p.read_bytes()
            manifest[key]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            z.writestr(key,data,compress_type=zipfile.ZIP_STORED if p.suffix in {'.gz','.parquet','.zip','.png'} else zipfile.ZIP_DEFLATED)
        z.writestr('MANIFEST.json',json.dumps({'project':'agent memory cycle 5','files':manifest},ensure_ascii=False,indent=1))
    os.replace(tmp,target)
    sha=hashlib.sha256(target.read_bytes()).hexdigest(); print(str(target),len(manifest),target.stat().st_size,sha)
if __name__=='__main__':main()
