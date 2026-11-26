"""Verify the public bundle without actor credentials, Click installation or grading data."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT/name).read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check():
    for name, want in read("manifest.json")["files"].items():
        assert digest((ROOT/name).read_bytes()) == want, name
    flow = read("profiles.json")
    obs = json.loads(gzip.decompress((ROOT/"responses.json.gz").read_bytes()))
    scout = read("scout.json")
    seal = read("packet-seal.json")
    all_ids = [i for action in scout["actions"] for i in action["receipts"]]
    summary = flow["scout"]
    assert summary["totals"]["quote_bytes"] == sum(scout["items"][i]["length"] for i in all_ids)
    assert summary["totals"]["quote_rendered"] == sum(len(scout["items"][i]["rendered"].encode()) for i in all_ids)
    assert summary["unique_quotes_rendered"] == sum(len(it["rendered"].encode()) for it in scout["items"])
    assert summary["unique_quote_bytes"] == sum(len(it["body"].encode()) for it in scout["items"])
    assert all(it["sha"] == digest(it["body"].encode()) for it in scout["items"])
    assert len(all_ids) == summary["totals"]["hits"] == 7
    prompt = (ROOT/"ACTOR_PROMPT.txt").read_text(encoding="utf8").rstrip("\r\n")
    size_only_url = "http://127.0.0.1:18878/v1/"+"x"*32
    decoded_total = 0
    wire_total = 0
    for actor in flow["actors"]:
        name = actor["actor"]
        expected = "".join(scout["items"][i]["rendered"] for i in scout["chosen"][actor["condition"]])
        packet = seal["packets"][actor["condition"]]
        assert digest(expected.encode()) == packet["sha"] and len(expected.encode()) == packet["bytes"]
        records = obs[name]
        assert [x["sequence"] for x in records] == list(range(1,len(records)+1))
        assert all(x["code"] == 200 for x in records)
        operations = Counter(x["request"]["op"] for x in records)
        assert operations == actor["operations"]
        source = Counter()
        for x in records:
            op, resp = x["request"]["op"], x["response"]
            if op in {"read","search"}:
                n = len(resp["text"].encode())
                assert n == resp["charged_bytes"]
                source[op] += n
        assert all(v == actor["bytes"][k] for k,v in source.items())
        assert sum(source.values()) == actor["source"]
        opening = records[0]["response"]
        assert records[0]["request"]["op"] == "start" and opening["memory"] == expected
        assert len(opening["issue"].encode()) == actor["issue"] == summary["issue_for_ranking"]
        assert len(expected.encode()) == actor["memory"]
        prompt_length = len(prompt.replace("{ACTOR}",name).replace("{ENDPOINT}",size_only_url).encode())
        assert prompt_length == actor["prompt"]
        decoded = prompt_length + actor["issue"] + actor["memory"] + sum(source.values())
        assert decoded == actor["prompt_issue_memory_source"]
        bodies = sum(len(json.dumps(x["response"],ensure_ascii=False).encode()) for x in records)
        assert bodies == actor["json_responses"] and bodies+prompt_length == actor["prompt_plus_json"]
        receipt = records[-1]["response"]
        assert records[-1]["request"]["op"] == "finish" and receipt["patch_sha256"] == actor["patch_sha256"]
        patch = (ROOT/"patches"/(name+".patch")).read_bytes()
        assert digest(patch) == receipt["patch_sha256"] and len(patch) == receipt["patch_bytes"] == actor["patch_bytes"]
        decoded_total += decoded
        wire_total += bodies + prompt_length
    assert (decoded_total,wire_total) == (26982,32811)
    assert (ROOT/"patches/actor-1.patch").read_bytes() == (ROOT/"patches/actor-3.patch").read_bytes()
    assert (ROOT/"patches/actor-1.patch").read_bytes() != (ROOT/"patches/actor-2.patch").read_bytes()
    print("PASS: manifest, frozen patches, three response streams, equal packet budgets, full measured input.")


if __name__ == "__main__":
    check()
