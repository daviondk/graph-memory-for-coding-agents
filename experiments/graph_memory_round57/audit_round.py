"""Cross-check published R57 counts and verify the recorded Git payload manifest."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
MANIFEST=HERE/"artifact-digests.json"


def data(name):
    return json.loads((HERE/name).read_bytes())


def metrics():
    rep=data("replication/results.json")
    assert rep["n"]==932
    base,new=(rep["pooled"][m] for m in ("own_norm","fill6_norm"))
    assert base["event_reads"]==new["event_reads"]==5953
    assert (base["bytes"],new["bytes"])==(280888,187864)
    assert data("anchor_risk/audit.json")["rankings"]==8418
    ranks=data("seed_pair/metrics.json")
    bounds=data("joint_certificate/results.json")
    certified=0
    count=0
    for panel in ("new","replication","long"):
        scored=ranks[panel]["pooled"]
        observed=bounds[panel]["pooled"]
        assert (scored["n"],scored["events"],scored["members"],scored["active"]) == (
                observed["n"],observed["build_events"],observed["build_members"],observed["has_joint"])
        count+=scored["n"]
        certified+=observed["initial_scores"]
    assert (count,certified)==(1153,1120)
    toy=data("seed_pair/ambiguity.json")
    assert toy["best_possible_pair_hits"]*2==toy["joint_hits"]==4096
    assert data("arb_multi/results.json")["all"]["n"]==105
    disk=data("block_index/results.json")
    mixed=data("composed/results.json")
    for panel in ("long","B"):
        all_files=[mixed[f"{panel}-continuous-{k}"] for k in ("flat","own","shared","lru")]
        assert {s["footprint"] for s in all_files}=={disk[panel+"-filelist"]["footprint"]}
        assert all_files[0]["all_body_bytes"]==disk[panel+"-filelist"]["counts"]["event_bytes"]
        assert all_files[0]["all_posting_bytes"]==disk[panel+"-filelist"]["counts"]["metadata_bytes"]
        assert len(all_files[0]["all_read_ns"][1])==5
    sensitivity = data("composed/lru-results.json")
    expected = {
        "long-continuous-shared": 21142, "long-restart-shared": 106781,
        "long-continuous-lru_unbounded": 91732, "long-restart-lru_unbounded": 91732,
        "B-continuous-shared": 6349, "B-restart-shared": 35228,
        "B-continuous-lru_unbounded": 14660, "B-restart-lru_unbounded": 25232,
    }
    for method, transferred in expected.items():
        stats = sensitivity[method]
        assert stats["all_body_bytes"] + stats["all_posting_bytes"] == transferred
        assert len(stats["all_read_ns"][1]) == 5
    with_media=data("walkthrough/verification.json")
    assert with_media["file_sha256"]==digest(HERE/"walkthrough/walkthrough.mp4")
    assert data("release/verification.json")["sha256"]==digest(HERE/"release/candidate.zip")
    print("Verified paired costs, independent ranking counts, durable layouts, paper package and media receipts.")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def files(seal):
    if seal:
        paths=subprocess.check_output(["git","ls-files","-z","--","."],cwd=HERE).decode().split("\0")
        names=sorted(n for n in paths if n and n!=MANIFEST.name)
    else:
        known=data(MANIFEST.name)
        names=sorted(known)
    result={n:digest(HERE/n) for n in names}
    if seal:
        MANIFEST.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    else:
        assert result==known
    print(len(names),"artifact hashes", "written" if seal else "verified")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seal",action="store_true")
    p.add_argument("--manifest",action="store_true")
    args=p.parse_args()
    metrics()
    if args.seal or args.manifest:
        files(args.seal)
