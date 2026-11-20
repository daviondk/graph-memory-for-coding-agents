from pathlib import Path
from zipfile import ZipFile
from tempfile import TemporaryDirectory
import hashlib, subprocess, sys, json, re, io
f=Path(__file__).resolve().parent; out=f.parents[1]/'outputs'
records=out/'agent-memory-experiment-records.zip'
word=out/'agent-memory-experiment-results.docx'
with ZipFile(word) as w:
    assert w.testzip() is None
    emb=w.read('word/embeddings/experiment-records.zip')
    assert emb==records.read_bytes()
    assert b'word/embeddings/experiment-records.zip' in w.read('[Content_Types].xml') or b'application/zip' in w.read('[Content_Types].xml')
    assert b'embeddings/experiment-records.zip' in w.read('word/_rels/document.xml.rels')
with ZipFile(io.BytesIO(emb)) as z:
    assert z.testzip() is None
    manifest=z.read('MANIFEST.sha256').decode().splitlines();assert len(manifest)==len(z.namelist())-1
    for l in manifest:
        digest,name=l.split('  ',1)
        assert hashlib.sha256(z.read(name)).hexdigest()==digest
    rnames=[s for s in z.namelist() if re.fullmatch(r'(?:search(?:_replication)?/runs|probe(?:_real)?/runs[12])/[^/]+\.json',s)]
    assert len(rnames)==120
    trials=[json.loads(z.read(s)) for s in rnames]
    threads=[e['thread_id'] for r in trials for a in r['attempts'] for e in a['events'] if e['type']=='thread.started']
    assert len(set(threads))==len(threads)==120
    assert all(r['status']=='ok' and len(r['attempts'])==1 and not r['attempts'][0]['actions'] for r in trials)
    assert not any(re.search(r'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{34,}',z.read(s).decode(errors='ignore')) for s in rnames)
    with TemporaryDirectory() as tmp:
        z.extractall(tmp)
        for script,args in [('shared/verify_package.py',[]),('probe_real/study_real.py',['audit']),('probe/audit.py',[]),('search_replication/audit_replication.py',[])]:
            res=subprocess.run([sys.executable,'-B','-X','utf8',script,*args],cwd=tmp,capture_output=True,text=True,encoding='utf-8',errors='replace')
            assert res.returncode==0,(script,res.stdout[-300:],res.stderr[-600:])
            print('verified',script)
print('sealed archive',len(manifest),'files,',len(trials),'research calls, all isolated; embedded bytes match')

