"""Freeze Git heads and verify only path changes in one filtered mirror at a time."""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
R57=HERE.parents[1]/"graph_memory_round57"
R59=HERE.parents[1]/"graph_memory_round59"
sys.path.insert(0,str(R57/"replication"))
from collect import canonical, git, load, remote, save, snapshot

PROJECTS=("sphinx-doc/alabaster","pydata/pydata-sphinx-theme","numpy/numpy-financial",
          "jazzband/tablib","python-poetry/tomlkit","pallets/jinja")


def earlier():
    roster=load(R57/"replication/data-seal.json")["earlier_rosters"].copy()
    for folder in [R57/"replication",R57/"seed_pair",R59/"holdout"]:
        roster[(folder/"heads.json").relative_to(HERE.parents[1]).as_posix()]=sorted(load(folder/"heads.json"))
    names={r.casefold() for entries in roster.values() for r in entries}
    assert len(names)==68 and not names.intersection(n.casefold() for n in PROJECTS)
    return roster


def inventory(rows):
    good=[i for i,(_,names) in enumerate(rows) if 2<=len(names)<=64]
    fence=len(good)//2
    begin=good[fence-1]+1 if fence else 0
    dense=[i for i in good if i>=64]
    sparse=[i for i in good if i>=len(rows)//2 and int(rows[i][0],16)%11==0]
    return dict(transitions=len(rows),changed_python_commits=sum(bool(p) for _,p in rows),
                unique_python_paths=len({path for _,paths in rows for path in paths}),
                eligible=len(good),fence=fence,oversize=sum(len(p)>64 for _,p in rows),
                all_dense=len(dense),all_sparse=len(sparse),
                post_dense=sum(i>=begin for i in dense),post_sparse=sum(i>=begin for i in sparse))


def run(args):
    roster=earlier()
    pins_file=HERE/"heads.json"
    if not pins_file.exists():
        save(pins_file,{name:remote(name) for name in PROJECTS})
    pins=load(pins_file)
    assert set(pins)==set(PROJECTS)
    datafile=HERE/"events.json.gz"
    prooffile=HERE/"raw-objects.json"
    data=load(datafile) if datafile.exists() else {}
    proofs=load(prooffile) if prooffile.exists() else {}
    if not args.verify_local:
        for name in PROJECTS:
            if not args.verify_git and name in data and name in proofs:
                continue
            with TemporaryDirectory(dir=HERE,prefix="mirror-") as temp:
                rows,pin,proof,size=snapshot(name,pins[name],temp)
                repo=Path(temp)/"repo"
                objects=Counter(git("cat-file","--batch-all-objects","--batch-check=%(objecttype)",repo=repo).decode().splitlines())
                assert set(objects)<= {"tree","commit","tag"} and objects["tree"]>0,objects
                assert size<100*1024**2
                record=dict(pin=pin,proof=proof,stored_object_types=dict(objects))
            if args.verify_git:
                assert data[name]==rows and proofs[name]["proof"]==proof and proofs[name]["pin"]==pin
                assert proofs[name]["stored_object_types"].get("blob",0)==0
            else:
                data[name]=rows
                proofs[name]={**record,"mirror_bytes_observed":size}
                save(datafile,data);save(prooffile,proofs)
            print(name,len(rows),size,"bytes; blob objects",objects["blob"],flush=True)
    assert set(data)==set(proofs)==set(PROJECTS)
    for name,rows in data.items():
        assert rows[-1][0]==pins[name]["head"]==proofs[name]["pin"]["head"]
        assert len(rows)==proofs[name]["pin"]["transitions"] and len(rows)<=1024
        assert all(paths==sorted(set(paths)) and all(path.endswith(".py") for path in paths) for _,paths in rows)
        assert proofs[name]["stored_object_types"].get("blob",0)==0
    summary=dict(earlier_unique_projects=68,source_rosters=roster,
              canonical_events_sha256=sha256(canonical(data)).hexdigest(),
              archive_sha256=sha256(datafile.read_bytes()).hexdigest(),
              protocol_sha256_lf=sha256((HERE/"PROTOCOL_RU.md").read_text(encoding="utf8").encode()).hexdigest(),
              per_project={k:inventory(v) for k,v in data.items()})
    keys=next(iter(summary["per_project"].values()))
    summary["totals"]={key:sum(x[key] for x in summary["per_project"].values()) for key in keys}
    # Sum of per-repository distinct counts, since path IDs are repository-local.
    if args.verify_git or args.verify_local:
        assert load(HERE/"panel.json")==summary
    else:
        save(HERE/"panel.json",summary)
    print(summary["totals"],summary["archive_sha256"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group()
    group.add_argument("--verify-git",action="store_true",help="Refetch every fixed HEAD unmodified")
    group.add_argument("--verify-local",action="store_true",help="Verify the archived inventory without a network")
    run(p.parse_args())
