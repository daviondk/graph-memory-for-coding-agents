"""Replay each registered verifier from a clean minimal study tree and a different current directory."""
import argparse,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
D=Path(__file__).resolve().parent
def main():
    cli=argparse.ArgumentParser();cli.add_argument('--out',type=Path);cli.add_argument('--scratch',type=Path);cli.add_argument('--quiet',action='store_true');args=cli.parse_args()
    release=json.loads((D/'release.json').read_bytes());results={}
    with tempfile.TemporaryDirectory(dir=args.scratch) as t:
        scratch=Path(t).resolve();r=scratch/'graph_memory_round47';r.mkdir();(scratch/'unrelated').mkdir()
        for n in release['top_documents']:
            if n.startswith('portable_inputs/'):
                dest=scratch/n.removeprefix('portable_inputs/');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(D/n,dest)
        for study in release['completed']:
            local=r/study;local.mkdir()
            src=D/study;m=json.loads((src/'manifest.json').read_bytes());files=m.get('files',m)
            for n in [*files,'manifest.json']:
                p=local/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/n,p)
            script='verify47.py' if study=='edge_placebo' else 'verify.py'
            cmd=[sys.executable,'-E','-s','-B','-X','utf8',str(local/script)]
            env={k:v for k,v in os.environ.items() if not k.startswith('PYTHON')}
            cp=subprocess.run(cmd,env=env,cwd=scratch/'unrelated',capture_output=True,timeout=180)
            if cp.returncode:raise RuntimeError(study+' '+cp.stderr.decode('utf8','replace')[-1300:])
            if not args.quiet:print(study,'verified',flush=True)
            results[study]=dict(script=script,exit=cp.returncode)
    if args.out:
        raw=(json.dumps(results,indent=2,sort_keys=True)+'\n').encode()
        if args.out.is_file():assert args.out.read_bytes()==raw
        else:args.out.write_bytes(raw)
if __name__=='__main__':main()
