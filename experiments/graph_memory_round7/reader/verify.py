"""Verify locked requests and responses, and check that grading restored the base files."""
from pathlib import Path
import json
import tarfile
import pilot
D = pilot.D

def main():
    ids = pilot.sealed()
    answer = pilot.read(D/"answer_lock.json")
    reqs = pilot.read(D/"requests.json.gz")
    assign = pilot.read(D/"assign.json")
    assert set(reqs) == {key for arms in assign.values() for key in arms.values()}
    assert len(answer["calls"]) == len(reqs)
    checked = 0
    for key, req in reqs.items():
        path = D/"calls"/(key+".json.gz")
        assert pilot.filehash(path) == answer["calls"][path.name]
        call = pilot.read(path)
        assert call["request"] == req and pilot.digest(pilot.canonical(req)) == key
        assert isinstance(call["response"]["choices"][0]["message"]["content"], str)
    grader = pilot.dependency()
    for i in ids:
        task = D/"tasks"/i
        grading = pilot.read(task/"grading.json")
        allowed = set(pilot.read(task/"packets.json.gz")["paths"])
        selected = allowed | grader.paths(grading["patch"]) | grader.paths(grading["test_patch"])
        archive = pilot.OLD/"tasks"/i/"checkout.tar.gz"
        assert pilot.read(task/"checkout_receipt.json")["sha256"] == pilot.filehash(archive)
        with tarfile.open(archive) as tar:
            members = {m.name.split("/",1)[1]:m for m in tar if m.isfile() and "/" in m.name}
            for rel in selected:
                path = task/"base"/rel
                if rel in members:
                    assert path.read_bytes() == tar.extractfile(members[rel]).read(), (i, rel)
                else:
                    assert not path.exists(), (i,rel)
                checked += 1
        for stage in ("solver","control"):
            assert (task/"grades_v2"/(stage+".json")).exists()
    outputs = [D/"rows.json",D/"results.json"]
    before = [pilot.filehash(path) for path in outputs]
    pilot.report()
    assert before == [pilot.filehash(path) for path in outputs]
    result = {"verified_tasks": len(ids), "verified_requests_and_responses": len(reqs),
              "restored_files_verified": checked, "result_sha256": before[1],
              "verification_script_sha256": pilot.filehash(Path(__file__))}
    pilot.save(D/"verification.json", result)
    print(json.dumps(result))

if __name__ == "__main__":
    main()
