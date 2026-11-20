"""Compact the exact generated artifacts and complete process transcripts for independent audit."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--study",type=Path,default=Path(__file__).resolve().parent)
    cli.add_argument("--evidence",type=Path,required=True)
    cli.add_argument("--canary-evidence",type=Path,help="reuse evidence from the unchanged reference and isolation suite")
    args=cli.parse_args()
    checksums={}
    entries=[]
    for source in ("canaries.jsonl","graded.jsonl"):
        entries.extend(json.loads(l) for l in (args.study/source).read_text("utf-8").splitlines())
    assert len(entries)==205
    dest=args.study/"grading-evidence.zip"
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for item in sorted(entries,key=lambda x:x["id"]):
            key=item["id"]
            is_ref=key.startswith("ref_") or key=="sandbox_surface"
            directory=(args.canary_evidence if args.canary_evidence and is_ref else args.evidence)/key
            if item["response_state"] != "missing_log":
                assert (directory/"grade.json").is_file(),str(directory)
            for name in ("grade.json","builder.stdout","builder.stderr","checker.stdout","checker.stderr","artifact.tar.gz"):
                p=directory/name
                if p.is_file():
                    raw=p.read_bytes()
                    member=f"{key}/{name}"
                    checksums[member]=hashlib.sha256(raw).hexdigest()
                    z.writestr(member,raw)
        z.writestr("SHA256.json",json.dumps(checksums,sort_keys=True,indent=2))
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(k)).hexdigest()==v for k,v in checksums.items())
    print(dest.name,dest.stat().st_size,"bytes",len(checksums),"verified records")


if __name__=="__main__":
    main()
