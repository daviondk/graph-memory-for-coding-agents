import collections
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIBLING = HERE.parent / "git_prediction"
sys.path.insert(0, str(SIBLING))
import run as gitbench

BAD = re.compile(r"secur|vulner|exploit|attack|malware|malicious|cve|ghsa|inject|payload|"
                 r"bypass|privilege|intrusion|unsafe|overflow|denial.of.service|traversal|"
                 r"deserializ|ssl|tls|certific|credential|password|saniti[sz]|"
                 r"authentic|authoriz|smuggl|forger|bioweap|pathogen|weapon", re.I)
LETTERS = "ABCDEFGH"
SYSTEM = ("You are helping a programmer find one other Python file that is likely to change with an already identified "
          "file. Choose one candidate. Use only the displayed historical data. Respond with one letter A through H.")


def digest(word):
    return hashlib.sha256(word.encode()).hexdigest()


def build(pin):
    repo = pin["repo"]
    path = SIBLING / "transfer_mirrors" / repo
    events = gitbench.changes(path, pin)
    # Titles are for screening only. No title is used for ranking or shown to the model.
    raw = gitbench.git(path, "log", "--first-parent", "--format=%H%x09%s", pin["sha"])
    titles = dict(s.split("\t", 1) for s in raw.decode(errors="replace").splitlines())
    memory = gitbench.Memory()
    pool = []
    for i, (sha, parents, ts, touched, deleted) in enumerate(events):
        if i >= len(events)//2 and 2 <= len(touched) <= 20 and not BAD.search(titles[sha]):
            anchor = touched[int(digest(f"{repo}:{i}"), 16) % len(touched)]
            if len(memory.active - {anchor}) >= 8:
                ranked, _ = memory.score(anchor, i)
                slate = ranked["lexical"][:4]
                for f in ranked["unit_smoothed"] + sorted(memory.active - {anchor}, key=lambda f: (-memory.frequency[f], f)):
                    if f not in slate and len(slate) < 8:
                        slate.append(f)
                assert len(slate) == 8 and anchor not in slate
                slate.sort(key=lambda f: digest(f"{repo}:{sha}:{f}"))
                raw_counts = memory.raw.get(anchor, {})
                unit_counts = memory.unit.get(anchor, {})
                evidence = [(raw_counts.get(f, 0), f"{unit_counts.get(f,0):.2f}") for f in slate]
                if len(set(evidence)) >= 2 and not any(BAD.search(f) for f in touched + slate):
                    pool.append({"repo": repo, "sha": sha, "parent": parents[0], "index": i,
                                 "anchor": anchor, "targets": [f for f in touched if f != anchor],
                                 "slate": slate, "counts": [memory.frequency[f] for f in slate],
                                 "evidence": evidence, "lex": ranked["lexical"][0], "graph": ranked["unit_smoothed"][0],
                                 "subject": titles[sha]})
        memory.observe(touched, deleted, i)
    return sorted(pool, key=lambda r: digest("reader:" + r["repo"] + r["sha"]))


def prompt(r, arm):
    pairs = r["evidence"]
    if arm == "shuffled":
        initial = int(digest("shuffle:"+r["sha"]), 16) % 7 + 1
        for k in range(7):
            offset = 1 + (initial + k - 1) % 7
            shifted = pairs[offset:] + pairs[:offset]
            if shifted != pairs:
                pairs = shifted
                break
        assert pairs != r["evidence"]
    if arm == "masked":
        pairs = [("?", "?")] * 8
    body = [f"Anchor path: {r['anchor']}",
            "For each candidate: prior = number of past changes to the file, shared = past changes also touching the anchor, "
            "weight = shared evidence discounted by how many other files each change touched. A question mark means unavailable.",
            "Select one additional path likely to change. Historical data:"]
    for letter, name, n, pair in zip(LETTERS, r["slate"], r["counts"], pairs):
        body.append(f"{letter} | {name} | prior={n} | shared={pair[0]} | weight={pair[1]}")
    return {"model":"qwen38-27b-ud-q4km", "messages":[{"role":"system","content":SYSTEM},
             {"role":"user","content":"\n".join(body)}], "max_tokens":8, "temperature":0, "seed":18112026,
            "cache_prompt": False, "stream": False, "chat_template_kwargs":{"enable_thinking":False}}


if __name__ == "__main__":
    pins = json.loads((SIBLING / "transfer_pins.json").read_text())
    pools = {p["repo"]: build(p) for p in pins if "sha" in p}
    order = sorted(pools, key=digest)
    selected = [pools[repo][i] for i in range(max(map(len, pools.values()))) for repo in order if i < len(pools[repo])][:24]
    assert len(selected) == 24
    (HERE / "selection.json").write_text(json.dumps(selected, indent=2), encoding="utf-8")
    calls = []
    for r in selected:
        for arm in sorted(["masked","true","shuffled"], key=lambda a: digest("order:"+r["sha"]+a)):
            calls.append({"repo":r["repo"],"sha":r["sha"],"arm":arm,"request":prompt(r,arm)})
    (HERE / "requests.jsonl").write_text("".join(json.dumps(v)+"\n" for v in calls), encoding="utf-8")
    (HERE / "selection_receipt.json").write_text(json.dumps({"eligible_by_repo":{k:len(v) for k,v in pools.items()},
         "selected_subjects":[r["subject"] for r in selected],
         "hashes":{f:gitbench.hash_file(HERE / f) for f in ["PROTOCOL.md","prepare.py","requests.jsonl","selection.json"]}}, indent=2), encoding="utf-8")
    print(json.dumps([r["subject"] for r in selected], indent=2))
