"""Read archives as data. Check exact prompt/model/earlier-state separation and obvious hidden paths."""
import argparse
import collections
import hashlib
import json
import re
import tarfile
from pathlib import Path

from analyze_action import lines


HIDDEN=re.compile(rb"(?<![\w-])/(?:oracle|bench|mnt/[cd]|run/WSL)(?:/|\b)")


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--study",type=Path,required=True)
    cli.add_argument("--evidence",type=Path,required=True)
    args=cli.parse_args()
    grades={g["id"]:g for g in lines(args.study/"graded.jsonl")}
    jobs=lines(args.study/"assigned.jsonl")
    assert len(jobs)==len(grades)==102
    leakage=[]
    links=[]
    truncations=collections.Counter()
    for j in jobs:
        key=j["id"]
        g=grades[key]
        raw=json.loads((args.study/"logs"/(key+".json")).read_text("utf-8"))
        assert raw["id"]==key
        assert (g.get("initial_tree_sha256") and g["checker"]["state"]=="ok")
        if g["response_state"]=="valid":
            src=json.loads(raw["text"])["builder"].encode()
            assert hashlib.sha256(src).hexdigest()==g["builder_sha256"]
            if HIDDEN.search(src):
                leakage.append([key,"builder"])
        with tarfile.open(args.evidence/key/"artifact.tar.gz","r:gz") as archive:
            for f in archive:
                assert f.name=="artifact" or f.name.startswith("artifact/")
                if f.issym() or f.islnk():
                    links.append([key,f.name,f.linkname])
                if f.isfile() and f.name.endswith((".py",".sh")):
                    stream=archive.extractfile(f)
                    if HIDDEN.search(stream.read()):
                        leakage.append([key,f.name])
        for stage in ("builder","checker"):
            for stream in ("stdout","stderr"):
                if g[stage].get(stream,{}).get("bytes",0)>8192:
                    truncations[stage+"_"+stream]+=1
    audit=dict(cells=len(jobs),source_hashes_verified=sum(g["response_state"]=="valid" for g in grades.values()),
               direct_hidden_path_matches=leakage,artifact_links=links,stderr_stdout_tails_truncated=dict(truncations),
               static_scope="literal /oracle, /bench, /mnt/c, /mnt/d or /run/WSL in builders and .py/.sh of resulting tree")
    (args.study/"artifact_audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(audit)


if __name__=="__main__":
    main()
