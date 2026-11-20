"""Verify the actual shipped archive after a clean extraction under drive D."""
from pathlib import Path
import argparse,json,subprocess,sys,tempfile,zipfile,datetime
ROOT=Path(__file__).resolve().parent
def main():
    zpath=ROOT.parents[1]/'outputs'/'agent-memory-session3-records.zip'
    scratch_root=ROOT.parents[2]/'x20-verification';scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_root,prefix='memory3-') as name:
        target=Path(name).resolve()
        assert target.is_relative_to(scratch_root.resolve()) and target.name.startswith('memory3-')
        with zipfile.ZipFile(zpath) as ar:
            for n in ar.namelist():assert (target/n).resolve().is_relative_to(target)
            ar.extractall(target)
        cp=subprocess.run([sys.executable,'-X','utf8',str(target/'verify_round.py')],cwd=target,capture_output=True)
        if cp.returncode:raise RuntimeError(cp.stderr.decode('utf8','replace')[-2500:])
        print(cp.stdout.decode('utf8','replace').strip(),flush=True)
        index=json.loads((target/'MANIFEST.sha256.json').read_bytes())
        print('fresh archive checked',len(index),'hashed files,',zpath.stat().st_size,'bytes')
if __name__=='__main__':main()
