import gzip,json,hashlib,sys
from pathlib import Path
from policy import decide
ROOT=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(fn):return json.loads(gzip.decompress((ROOT/fn).read_bytes()))
def rows(corpus):
    for system,sessions in sorted(corpus.items()):
        for idx,session in enumerate(sessions):
            if idx<len(sessions)-300:continue
            past=sorted((s for s in sessions[:idx] if s['end'] < session['start']),key=lambda s:(s['end'],s['id']))[-15:]
            if len(past)<15 or len(session['tests'])<8:continue
            roster=sorted(k for k,y in session['tests'])
            probes=sorted(roster,key=lambda t:hashlib.sha256(f's5-probe|{system}|{session["id"]}|{t}'.encode()).digest())[:6]
            pending=sorted(set(roster)-set(probes))
            # Only the six prefix outcomes cross into decide.
            env=dict(session['tests']); observed=[env[k] for k in probes]
            choices=decide([dict(s['tests']) for s in past],pending,probes,observed)
            yield {'sys':system,'id':session['id'],'past':[s['id'] for s in past],'probes':list(zip(probes,observed)),'methods':choices}
def main():
    import numpy as np
    lock={f:digest(ROOT/f) for f in ('PROTOCOL.md','SCHEMA.md','policy.py','predict.py','score.py','cycles.json.gz')}
    (ROOT/'input_lock.json').write_text(json.dumps({'files':lock,'numpy':np.__version__,'python':sys.version},indent=2))
    with gzip.GzipFile(str(ROOT/'rankings.jsonl.gz'),'wb',compresslevel=3,mtime=0) as fp:
        for row in rows(read('cycles.json.gz')):fp.write((json.dumps(row,separators=(',',':'))+'\n').encode())
    (ROOT/'decision_lock.json').write_text(json.dumps({'rankings.jsonl.gz':digest(ROOT/'rankings.jsonl.gz'),'input_lock.json':digest(ROOT/'input_lock.json')},indent=2))
if __name__=='__main__':main()
