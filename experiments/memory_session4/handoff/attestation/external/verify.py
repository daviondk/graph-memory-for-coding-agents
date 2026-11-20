"""Offline structural and source-projection audit. Stdlib, optional git patch-id checks."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
ROOT = Path(__file__).resolve().parent

def digest(body):
    return hashlib.sha256(body).hexdigest()

def read(name):
    data = (ROOT / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

def signature(body):
    result = []
    active = None
    hunk = False
    for line in body.decode("utf8",errors="replace").splitlines():
        if line.startswith("diff --git "):
            active = [line,[]]
            result.append(active)
            hunk = False
        elif line.startswith("@@"):
            hunk = True
        elif active is not None and hunk and line[:1] in ["+","-"]:
            active[1].append(line)
    return result if any(item[1] for item in result) else None

def gitid(body):
    if not body.strip():
        return None
    result = subprocess.run(["git","patch-id","--stable"],input=body,capture_output=True)
    parts = result.stdout.split()
    return parts[0].decode() if result.returncode == 0 and parts and re.fullmatch(b"[a-f0-9]{40}",parts[0]) else None

def main():
    for lock in ("selection_lock.json","checksums.json"):
        if (ROOT/lock).exists():
            for file, expected in read(lock).items():
                source = ROOT/file
                if not source.exists() and file == "../EXTERNAL_PROTOCOL.md":
                    source = ROOT/"EXTERNAL_PROTOCOL.md"
                assert digest(source.read_bytes()) == expected, (lock,file)
    selection = read("selection.json")
    top = read("top_listing.json")
    candidates = sorted(prefix.split("/")[1] for prefix in top["folders"]
                        if "mini" in prefix.split("/")[1].lower()
                        and prefix.split("/")[1] not in selection["excluded_anchors"])
    assert candidates == [folder["folder"] for folder in selection["folders"]]
    expected_pairs = set()
    selected_sources = {}
    for folder in selection["folders"]:
        name = folder["folder"]
        assert "mini" in name.lower() and name not in selection["excluded_anchors"]
        if "listing_error" in folder:
            continue
        inventory = read("inventory/"+name+".json.gz")
        patches = {}
        traces = {}
        for obj in inventory["listing"]["objects"]:
            path = obj["key"].removeprefix("bash-only/"+name+"/")
            p = re.fullmatch(r"logs/([^/]+)/patch\.diff",path)
            t = re.fullmatch(r"trajs/(?:([^/]+)/)?([^/]+)\.traj\.json",path)
            if p:
                patches[p[1]] = obj
            if t and (t[1] is None or t[1] == t[2]):
                assert t[2] not in traces
                traces[t[2]] = obj
        ids = sorted(patches.keys() & traces.keys(),key=lambda issue:digest(("public-link-audit-v1|"+name+"|"+issue).encode()))[:24]
        assert ids == [item["id"] for item in folder["selection"]], name
        for item in folder["selection"]:
            assert item["patch"] == patches[item["id"]] and item["trace"] == traces[item["id"]]
            expected_pairs.add((name,item["id"]))
            selected_sources[(name,item["id"])] = item
    rows = read("records.json.gz")
    assert len(rows) == len({(row["folder"],row["id"]) for row in rows})
    assert expected_pairs == {(row["folder"],row["id"]) for row in rows}
    counts = collections.Counter()
    git_available = shutil.which("git") is not None
    for row in rows:
        if "error" in row:
            counts["errors"] += 1
            continue
        prefix = "records/"+row["folder"]+"/"+row["id"]
        selected = selected_sources[(row["folder"],row["id"])]
        for kind in ("trace","patch"):
            assert row[kind]["bytes"] == selected[kind]["bytes"]
            assert row[kind]["etag"] == selected[kind]["etag"]
            assert row[kind]["url"] == "https://swe-bench-submissions.s3.amazonaws.com/" + urllib.parse.quote(selected[kind]["key"], safe="/")
            assert re.fullmatch("[0-9a-f]{64}",row[kind]["sha256"])
        patch = (ROOT/(prefix+".evaluator.patch")).read_bytes()
        assert digest(patch) == row["patch"]["sha256"]
        assert len(patch) == row["patch"]["bytes"]
        if row["patch"]["md5_verified"]:
            assert hashlib.md5(patch).hexdigest() == row["patch"]["etag"]
        c = row["comparison"]
        counts["known"] += c["known_submission"]
        if not c["known_submission"]:
            assert row["submission_sha256"] is None
            assert c["bytes_equal_nonempty"] is c["signed_changes_equal"] is c["git_patch_id_equal"] is None
            continue
        submitted = (ROOT/(prefix+".trajectory.patch")).read_bytes()
        assert digest(submitted) == row["submission_sha256"]
        both = bool(patch.strip() and submitted.strip())
        assert c["both_nonempty"] == both
        assert c["bytes_equal_nonempty"] == (patch==submitted if both else None)
        a,b = signature(patch),signature(submitted)
        expected_signed = a==b if both and a is not None and b is not None else None
        assert c["signed_changes_equal"] == expected_signed
        if git_available:
            pa,pb = gitid(patch),gitid(submitted)
            assert c["patch_id"] == pa and c["submission_patch_id"] == pb
            assert c["git_patch_id_equal"] == (pa==pb if both and pa is not None and pb is not None else None)
        counts["byte_same"] += c["bytes_equal_nonempty"] is True
        counts["byte_different"] += c["bytes_equal_nonempty"] is False
        counts["signed_different"] += c["signed_changes_equal"] is False
        counts["patchid_different"] += c["git_patch_id_equal"] is False
    summary = read("summary.json")
    assert summary["sampled"] == len(rows)
    for folder, group in summary["folders"].items():
        subset = [row for row in rows if row["folder"] == folder]
        assert group["selected"] == len(subset)
        for metric in ("bytes_equal_nonempty","signed_changes_equal","git_patch_id_equal"):
            vals = [row["comparison"][metric] for row in subset if "comparison" in row]
            assert group[metric] == {"equal":vals.count(True),"different":vals.count(False),"unknown_or_empty":vals.count(None)}
    print("PASS",len(expected_pairs),"sampled pairs",dict(counts),"git independently rechecked",git_available)
    print("Raw trajectory payloads were discarded; their fetch-time SHA/MD5 receipts are preserved. Offline verification checks stored projections, not original trace bodies.")

if __name__ == "__main__":
    main()

