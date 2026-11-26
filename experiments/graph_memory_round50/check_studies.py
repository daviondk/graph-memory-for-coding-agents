"""Replay registered numerical verifiers in the complete research repository."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from verify_release import directory

def policy_sensitivity(root):
    """Secondary margin rule versus always following an available mention on the same token inputs."""
    import gzip
    import numpy as np
    summary={}
    for name in ("adaptive_address","gate_confirmation"):
        cases=json.loads(gzip.decompress((root/name/"outcomes.json.gz").read_bytes()))
        assert len({v["cluster"] for v in cases.values()})==len(cases)
        differences=np.array([r["arms"]["adaptive"][1]-r["arms"]["linked_dense"][1] for _,r in sorted(cases.items())])
        rng=np.random.default_rng(50088)
        draws=[]
        for _ in range(100):
            indices=rng.integers(0,len(cases),size=(100,len(cases)))
            draws.extend(differences[indices].mean(axis=1))
        summary[name]=dict(delta_pp=100*float(differences.mean()),
                           ci95_pp=np.percentile(100*np.asarray(draws),[2.5,97.5]).tolist())
    return summary

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--scratch",type=Path)
    cli.add_argument("--out",type=Path)
    args=cli.parse_args()
    root=Path(__file__).resolve().parent
    release,_=directory(root);checks={"paired_policy_sensitivity":policy_sensitivity(root)}
    with TemporaryDirectory(dir=args.scratch) as tmp:
        env=dict(os.environ,TEMP=tmp,TMP=tmp,PYTHONDONTWRITEBYTECODE="1",
                 OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
        for name in release["requested"]:
            if name=="benchmark_audit":
                checks[name]="Literature and source audit; integrity checked."
                continue
            verifier=root/name/"verify.py"
            if name=="address_demo" and not verifier.is_file():
                verifier=root/name/"verify_smoke.py"
            if not verifier.is_file():raise RuntimeError("Missing numerical check: "+name)
            result=subprocess.run([sys.executable,"-B","-X","utf8",str(verifier)],cwd=verifier.parent,env=env,
                    capture_output=True,text=True,encoding="utf8",errors="replace",timeout=1200)
            if result.returncode:raise RuntimeError(name+"\n"+result.stdout[-1500:]+result.stderr[-1500:])
            checks[name]=result.stdout.strip()[-1500:]
            print(name,"OK",flush=True)
    directory(root)
    if args.out:args.out.write_text(json.dumps(checks,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":main()

