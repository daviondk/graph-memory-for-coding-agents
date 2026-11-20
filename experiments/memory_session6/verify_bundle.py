"""Check the archived hashes and replay research tables without a model or network."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src,'sha256').hexdigest()

def check(root, full):
    manifest=json.loads((root/'MANIFEST.json').read_bytes())['entries']
    for name,expected in manifest.items():
        p=root/name
        assert p.is_file() and p.stat().st_size==expected['bytes'] and sha(p)==expected['sha256'], name
    repair=json.loads((root/'repair/delivery_manifest.json').read_bytes())['hashes']
    for name,digest in repair.items():
        assert sha(root/'repair'/name)==digest,name
    subcounts={}
    for folder in ('concord/controls','validity/admission'):
        listed=json.loads((root/folder/'manifest.json').read_bytes())['hashes']
        for name,digest in listed.items():
            assert sha(root/folder/name)==digest,folder+'/'+name
        subcounts[folder]=len(listed)
    results=[]
    if full:
        commands=[
            ('inventory.py',[]),
            ('validity/verify.py',[]),
            ('validity/admission/verify.py',[]),
            ('reader/standalone_check.py',[]),
            ('reader/transfer/frozen_transfer.py',['--offline']),
            ('reader/calibration/calibrate.py',[]),
            ('reader/calibration/audit.py',[]),
            ('literature/replay.py',[]),
            ('literature/paired_power.py',[]),
            ('literature/chains/check.py',[]),
            ('literature/chains/write/retain.py',[]),
            ('literature/chains/write/grade.py',[]),
            ('literature/chains/cue/verify.py',[]),
            ('literature/chains/gate/verify_gate.py',[]),
            ('literature/chains/merge_times/audit.py',[]),
            ('repair/verify.py',[]),
            ('repair/cap_report.py',[]),
            ('concord/verify.py',[]),
            ('concord/grade.py',['--offline']),
            ('concord/judge/score.py',[]),
            ('concord/judge/audit.py',[]),
            ('concord/highlight/verify_highlight.py',[]),
            ('concord/highlight/grade_highlight.py',['--offline']),
            ('concord/highlight_judge/verify.py',[]),
            ('concord/controls/verify.py',[]),
        ]
        env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','TEMP':str(root),'TMP':str(root)}
        for name,args in commands:
            path=root/name
            sub=subprocess.run([sys.executable,'-B',str(path),*args],cwd=path.parent,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',errors='replace')
            if sub.returncode:
                raise RuntimeError(name+' failed: '+sub.stdout[-2200:])
            results.append(name)
            print('PASS',name,flush=True)
        for name,expected in manifest.items():
            assert sha(root/name)==expected['sha256'], 'replay modified '+name
    return dict(sha256_files_verified=len(manifest),mbpp_delivery_hashes_verified=len(repair),subsets=subcounts,offline_replays=results)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path,nargs='?')
    parser.add_argument('--hash-only',action='store_true')
    parser.add_argument('--receipt',type=Path)
    args=parser.parse_args()
    if args.archive:
        with tempfile.TemporaryDirectory(dir=args.archive.resolve().parent,prefix='cycle6-verification-') as td:
            dest=Path(td).resolve()
            with zipfile.ZipFile(args.archive) as archive:
                for item in archive.infolist():
                    assert (dest/item.filename).resolve().is_relative_to(dest),item.filename
                archive.extractall(dest)
            receipt=check(dest,not args.hash_only)
            receipt.update(archive_bytes=args.archive.stat().st_size,archive_sha256=sha(args.archive))
    else:
        receipt=check(ROOT,not args.hash_only)
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    main()
