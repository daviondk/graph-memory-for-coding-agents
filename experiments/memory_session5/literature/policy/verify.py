"""Offline replay of archived study and masking check from projected observable inputs."""
import contextlib, hashlib, io, json, os, shutil, tempfile
from pathlib import Path
import study, transfer
ROOT=Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify():
    audits=json.loads((ROOT/'receipts.json').read_bytes())
    for row in audits:
        f=ROOT/'sources'/Path(row['path']).name
        assert f.stat().st_size==row['size'] and sha(f)==row['sha256'],f
    checked=[]
    with tempfile.TemporaryDirectory(prefix='audit_',dir=ROOT) as temp:
        dest=Path(temp)
        (dest/'sources').mkdir()
        for name in ('tokenizer.json','transfer_inputs.json.gz'):
            os.link(ROOT/name,dest/name)
        for f in (ROOT/'sources').iterdir():os.link(f,dest/'sources'/f.name)
        study.ROOT=dest;study.SRC=dest/'sources';transfer.ROOT=dest
        with contextlib.redirect_stdout(io.StringIO()):
            study.main();transfer.main()
        for file in sorted(dest.iterdir()):
            if not file.is_file() or file.name in ('tokenizer.json','transfer_inputs.json.gz'):continue
            # gzip headers can differ between Python versions, so compare payloads.
            assert transfer.load(file)==transfer.load(ROOT/file.name),file
            checked.append(file.name)
    receipt={'passed':True,'released_blobs':len(audits),'recomputed_files':checked}
    (ROOT/'verify.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(receipt)

if __name__=='__main__':verify()
