"""Export only public production sources; verifies the same bytes again against the official checkout."""
import hashlib,json,tarfile,subprocess,io
from pathlib import Path,PurePosixPath
D=Path(__file__).resolve().parent
P=Path("D:/CodexResearch/x20-r49-woodwork-actors")
TARGET="alteryx__woodwork-640"
PARQUET="22238743ca143276e3ff4616f569b3921c42945bfee1a6aa8fa376a02feebb98"
def hashbytes(s):return hashlib.sha256(s).hexdigest()
def allowed(p):
    return len(p.parts)>1 and p.parts[0]=="woodwork" and p.suffix==".py" and not any(x in {"tests","test","__pycache__"} or x.startswith("test_") or x.endswith("_test.py") for x in p.parts)
def main():
    screened=json.loads((D/"screen.json").read_bytes());assert screened["data_sha256"]==PARQUET
    row=next(x for x in screened["rows"] if x["instance_id"]==TARGET)
    assert row['base_commit']=='7bde24e9c9b5c5a0e228b4c62c094fced9901c3b'
    (P/'problem.txt').write_bytes(row['problem_statement'].encode())
    def export(t,strip):
        data={}
        for m in t:
            path=PurePosixPath(m.name)
            if strip:path=PurePosixPath(*path.parts[1:])
            if not m.isfile() or not allowed(path):continue
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in str(path)
            data[str(path)]=t.extractfile(m).read()
        return data
    with tarfile.open(P/'base.tar.gz') as t: a=export(t,True)
    assert len(a)>20
    for k,b in a.items():
        dest=P/'repository'/k;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(b)
    snap=hashbytes(json.dumps({k:hashbytes(b) for k,b in a.items()},sort_keys=True).encode())
    receipt=dict(instance=TARGET,commit=row['base_commit'],image=row['image'],issue=hashbytes(row['problem_statement'].encode()),production_files=len(a),snapshot=snap,tar_sha256=hashbytes((P/'base.tar.gz').read_bytes()),protocol=hashbytes((D/'PROTOCOL_RU.md').read_bytes()))
    (D/'registration.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    import sys
    if '--verify-image' in sys.argv:
        cmd=['docker','run','--rm','--network','none','-w','/woodwork',row['image']]
        head=subprocess.check_output([*cmd,'git','rev-parse','HEAD']).decode().strip()
        assert head==row['base_commit']
        with tarfile.open(fileobj=io.BytesIO(subprocess.check_output([*cmd,'git','archive','HEAD','woodwork']))) as t: b=export(t,False)
        assert a==b
        print(len(a),'production sources match at',head)
if __name__=='__main__':main()
