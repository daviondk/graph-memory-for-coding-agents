"""Package the small upstream dependencies and check evaluation in an isolated directory."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]


def main():
    manifests=[json.loads((HERE/f).read_bytes())['files'] for f in ('method_lock.json','dependency_lock.json','headroom_lock.json','state_lock.json','evaluation_lock.json')]
    checked={}
    for manifest in manifests:
        for p,h in manifest.items():
            assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h,p
            checked[(HERE/p).resolve()]=h
    upstream={p for p in checked if not p.is_relative_to(HERE)}
    archive=HERE/'upstream_inputs.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for path in sorted(upstream):
            z.write(path,path.relative_to(WORK))
    with tempfile.TemporaryDirectory(dir=HERE) as name:
        root=Path(name)
        with zipfile.ZipFile(archive) as z: z.extractall(root)
        version=root/HERE.relative_to(WORK)
        for path in [*checked.keys(),HERE/'method_lock.json',HERE/'state_lock.json',HERE/'score.py']:
            if not path.is_relative_to(HERE): continue
            target=version/path.relative_to(HERE)
            if target.exists(): continue
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
        run=subprocess.run([sys.executable,'-B','score.py'],cwd=version,capture_output=True,text=True)
        if run.returncode: raise RuntimeError(run.stderr)
        assert (version/'results.json').read_bytes()==(HERE/'results.json').read_bytes()
    (HERE/'package_verification.json').write_text(json.dumps(dict(upstream_files=len(upstream),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),scored_isolated_tree=True,results_byte_exact=True),indent=1))


if __name__=='__main__': main()
