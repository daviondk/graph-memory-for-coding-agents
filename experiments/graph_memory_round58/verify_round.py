"""Cross-check the public claims and every versioned payload in the round."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
MANIFEST=HERE/"artifact-digests.json"


def read(path):
    return json.loads((HERE/path).read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def cross_check():
    natural=read("restart_transfer/no-padding.json")["aggregate"]
    for panel,values in {
        "original-long":(106781,106174,88554,82907,69607),
        "original-B":(34309,13550,12301,12255,12168),
        "external-long":(30987,37031,32878,32566,39868),
        "external-B":(335947,197178,148325,146115,131923),
    }.items():
        assert tuple(natural[panel][m]["charged"] for m in
                     ("cold","recent1024","largest1024","demand1024","full"))==values
    valid=read("checkpoint_value/results.json")
    net=read("checkpoint_value/natural-results.json")["summary"]
    assert len(valid["cases"])==33
    v=valid["groups"]["original/long"]
    assert (v["demand1024_body"],v["demand1024_posting"],v["lo"],v["hi"])==(30078,0,33439,33439)
    assert sum(net[p+"-long"]["lower"] for p in ("replication","seed_pair"))==7768
    assert sum(net[p+"-long"]["upper"] for p in ("replication","seed_pair"))==7798
    d=read("decision/results.json")["transfer"]["all"]["full"]
    assert [d[m]["bytes"] for m in ("primary","fixed","given_horizon","oracle")]==[179374,171791,169927,157542]
    f=read("frontier/results.json")
    i=read("incremental/results.json")
    for key in ("long","B"):
        assert sum(f[key]["sql"][s] for s in ("body_bytes","posting_bytes"))==i[key]["1024/flat"]["bytes"]
    assert read("frontier/check.json")["decoded"]==29160
    transfer=read("incremental/transfer-results.json")
    assert len(transfer["projects"])==24
    assert sum(t["queries"] for key,t in transfer["projects"].items() if key.split("/")[1]=="B")==3866
    a=read("solver/results.json")["arms"]
    assert (a["static"]["n"],a["static"]["all_pass"],a["adaptive"]["all_pass"])==(21,7,7)
    assert (a["static"]["passed_examples"],a["adaptive"]["passed_examples"])==(46,46)
    assert read("demo/ui-check.json")["html_sha256"]==digest(HERE/"demo/index.html")
    media=read("walkthrough/verification.json")
    assert media["file_sha256"]==digest(HERE/"walkthrough/walkthrough.mp4")
    assert media["captions_sha256"]==digest(HERE/"walkthrough/captions.srt")
    assert len(media["verified_scenes"])==10
    assert read("manuscript/verification.json")["sha256"]["paper.pdf"]==digest(HERE/"manuscript/paper.pdf")
    assert read("release/verification.json")["sha256"]==digest(HERE/"release/candidate.zip")
    print("Verified archive costs, exact and bounded optima, transfer workloads, model scores and release receipts.")


def verify_manifest(seal):
    items=subprocess.check_output(["git","ls-files","-z","--","."],cwd=HERE).decode("utf8").split("\0")
    payload={name:digest(HERE/name) for name in sorted(items) if name and name!=MANIFEST.name}
    if seal:
        MANIFEST.write_bytes((json.dumps(payload,indent=2)+"\n").encode())
    else:
        assert read(MANIFEST.name)==payload
    print(len(payload),"tracked artifact digests", "written" if seal else "match")


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    options=ap.add_mutually_exclusive_group()
    options.add_argument("--seal",action="store_true")
    options.add_argument("--manifest",action="store_true")
    args=ap.parse_args()
    cross_check()
    if args.manifest or args.seal:
        verify_manifest(args.seal)
