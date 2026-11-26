"""Verify the portable evidence bundle using the Python standard library."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(name):
    return json.loads((ROOT/name).read_bytes())

def require(condition, label):
    if not condition:
        raise ValueError(label)

if __name__ == "__main__":
    files = read("manifest.json")["files"]
    for name, expected in files.items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == expected, name)
    screen = read("screen.json")
    require(screen["protocol_sha256"] == sha(ROOT/"PROTOCOL.md"), "screen protocol")
    require(screen["rows"] == 111 and len(screen["ledger"]) == 21, "screen population")
    require([s["rank"] for s in screen["selected"]] == [15, 21], "selected ranks")
    for target in screen["selected"]:
        path = ROOT/"specs"/target["instance"]
        histories = json.loads((path/"history-minimum.json").read_bytes())
        require(len({h["id"] for h in histories}) == 3 and all(h["ancestor"] and h["target_id_hits"] == 0 and h["verified_hf"] and h["accepted"] for h in histories), "history provenance")
        require(sha(path/"SOURCE_LICENSE.txt") in {r["sha256"] for r in target["archive"]["licenses"]}, "source license")
    target = screen["selected"][0]
    case_dir = ROOT/"specs"/target["instance"]
    case = json.loads((case_dir/"case.json").read_bytes())
    ids = set(case["FAIL_TO_PASS"] + case["PASS_TO_PASS"])
    for variant in ("base", "reference"):
        prefix = ROOT/"smoke"/("native-"+variant)
        r = json.loads(prefix.with_suffix(".json").read_bytes())
        is_reference = variant == "reference"
        require(r["evaluator_sha256"] == sha(ROOT/"grade_patch.py") and r["source_archive_sha256"] == target["archive"]["sha256"] and r["official_test_patch_sha256"] == sha(case_dir/"test_patch.diff"), "active evaluator inputs")
        require(r["patch_sha256"] == (sha(case_dir/"patch.diff") if is_reference else hashlib.sha256(b"").hexdigest()), "patch identity")
        require(r["official_parser_sha256"] == "818560dab8da86cecc31cd9484a0f2b770359e59c51613316a391b58a73885e1" and r["official_exact_scorer_sha256"] == "e580d953b75e5182a66ffd2fecfbf9c756dadd89db767cfd42bd251f956a7108", "upstream scorer identities")
        require(r["log_sha256"] == sha(prefix.with_suffix(".log")) and r["junit_sha256"] == sha(prefix.with_suffix(".xml")), "raw evidence hashes")
        suite = ET.parse(prefix.with_suffix(".xml")).find("testsuite")
        require(suite is not None and int(suite.attrib["tests"]) == 9 and int(suite.attrib["skipped"]) == 1 and int(suite.attrib["failures"]) == int(not is_reference), "independent JUnit")
        require(r["pass_to_pass"] == [7,7] and r["fail_to_pass"] == [int(is_reference),1], "registered counts")
        require(r["package_import_in_private_checkout"] and r["complete_observation"] and r["paper_optional_packages"] and all(r["native_statuses"][i] == r["junit_statuses"][i] for i in ids), "registered ID agreement")
        require(r["official_exact_passed_match"] == is_reference and r["registered_success"] == is_reference, "native scorer controls")
    print(f"Verified {len(files)} signed files, 2 target provenance records and both PyBaMM controls.")
