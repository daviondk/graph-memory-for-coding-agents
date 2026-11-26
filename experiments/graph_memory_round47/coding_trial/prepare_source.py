"""Prepare the public, unmodified issue and base snapshot only. No answer or hidden test field is requested."""
from hashlib import sha256
from pathlib import Path,PurePosixPath
import argparse, json,tarfile
TARGET='pallets__click-1915';COMMIT='329b1001755452c96dcefcf4a3c799a2463710e0'
TAR='33af7a4343c8d1b090f194c28cfed328d03d2301be800ac98a9811584d7975eb'
PARQUET='22238743ca143276e3ff4616f569b3921c42945bfee1a6aa8fa376a02feebb98'
def raw(path):return sha256(path.read_bytes()).hexdigest()
def entries(path):
    assert raw(path)==TAR
    with tarfile.open(path,'r:gz') as tar:
        for m in tar:
            if m.isdir():continue
            assert m.isfile(),m.name
            p=PurePosixPath(m.name);assert p.parts[0]=='click-'+COMMIT and len(p.parts)>1 and not p.is_absolute() and all(v not in {'..','.git'} and ':' not in v and '\\' not in v for v in p.parts)
            yield '/'.join(p.parts[1:]),tar.extractfile(m).read()
def main():
    import pyarrow.parquet as pq
    cli=argparse.ArgumentParser();cli.add_argument('benchmark',type=Path);cli.add_argument('clean',type=Path);args=cli.parse_args()
    src=args.clean;assert raw(args.benchmark)==PARQUET
    row=pq.read_table(args.benchmark,columns=['instance_id','repo','base_commit','problem_statement'],filters=[('instance_id','=',TARGET)]).to_pylist()[0]
    assert row['base_commit']==COMMIT and row['repo']=='pallets/click'
    facts={}
    for n,b in entries(src/'base.tar.gz'):
        f=src/'repository'/n;f.parent.mkdir(parents=True,exist_ok=True)
        if f.exists():assert f.read_bytes()==b
        else:f.write_bytes(b)
        facts[n]=[len(b),sha256(b).hexdigest()]
    observed={p.relative_to(src/'repository').as_posix() for p in (src/'repository').rglob('*') if p.is_file()}
    assert observed==set(facts)
    issue=row['problem_statement'].encode('utf8');(src/'problem.txt').write_bytes(issue)
    receipt={'instance':TARGET,'base':COMMIT,'source':'https://codeload.github.com/pallets/click/tar.gz/'+COMMIT,'archive_sha256':TAR,
             'archive_bytes':(src/'base.tar.gz').stat().st_size,'files':len(facts),'total_bytes':sum(v[0] for v in facts.values()),'issue_sha256':sha256(issue).hexdigest(),'issue_bytes':len(issue),
             'source_content_sha256':sha256(json.dumps(facts,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    b=(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode();(src/'source.json').write_bytes(b);print(json.dumps(receipt))
if __name__=='__main__':main()
