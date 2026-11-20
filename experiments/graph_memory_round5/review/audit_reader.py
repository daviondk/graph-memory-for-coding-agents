"""Independent audit of sealed R5 inputs, GPU responses, golds and duplicate opportunities."""
import argparse
import collections
import datetime
import gzip
import hashlib
import json
import math
import re
from functools import cache
from pathlib import Path

import pyarrow.parquet as parquet

HERE = Path(__file__).resolve().parent
READER = HERE.parent / "reader"
SOURCE = HERE.parent.parent / "graph_memory_round4/repo"
IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
NEAR_MIN_CHARS = 20
NEAR_MIN_IDS = 2


@cache
def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def check_files(root, manifest):
    for name, checksum in manifest.items():
        check(digest(root / name) == checksum, name + " SHA256 mismatch")


def load_inputs(panel):
    inputs = read(READER / f"{panel}_data_lock.json")
    check_files(READER, inputs["sha"])
    check_files(SOURCE / "archive_inputs", inputs["source"])
    check(digest(SOURCE / "archive.pred.jsonl.gz") == inputs["ranks"], "rank lock")
    packets = read(READER / f"{panel}_packets.json.gz")
    check(len(packets) == inputs["n"], "count and lock")
    check(dict(collections.Counter(p["panel"] for p in packets)) == inputs["strata"], "strata and lock")
    check(len({p["repo"] for p in packets}) == len(packets), "one row per project")
    check(len({p["id"] for p in packets}) == len(packets), "IDs repeat")
    return packets


def similarity_float(a, b):
    # Symmetric normalized Indel distance from a bit-parallel LCS, independent of the reader scorer.
    if a == b:
        return 100.
    positions = {}
    for j, char in enumerate(b):
        positions[char] = positions.get(char, 0) | (1 << j)
    state = 0
    for char in a:
        merged = positions.get(char, 0) | state
        state = merged & ~(merged - (state * 2 + 1))
    return 200 * state.bit_count() / (len(a) + len(b))


def lines(text):
    return [s.strip() for s in text.splitlines() if s.strip()]


def overlap(text, gold):
    candidates = lines(text)
    exact = gold in candidates
    eligible = len(gold) >= NEAR_MIN_CHARS and len(IDENTIFIER.findall(gold)) >= NEAR_MIN_IDS
    near = eligible and any(
        200 * min(len(gold), len(c)) >= 90 * (len(gold) + len(c)) and similarity_float(gold, c) >= 90
        for c in candidates)
    return {"exact": exact, "near": near, "near_eligible": eligible}


def extract(raw):
    return next((s for s in lines(raw) if not s.startswith(chr(96) * 3)), "")


def idf1(proposed, gold):
    lhs = set(IDENTIFIER.findall(proposed))
    rhs = set(IDENTIFIER.findall(gold))
    return 2 * len(lhs & rhs) / (len(lhs) + len(rhs)) if lhs or rhs else 1.


def source_rows(packets):
    refpath = READER / "original_targets.json.gz"
    check(refpath.exists() and (READER / "original_targets_receipt.json").is_file(), "original target sidecar not sealed")
    receipt = read(READER / "original_targets_receipt.json")
    check(digest(refpath) == receipt["lock"], "original sidecar SHA mismatch")
    for key, checksum in receipt["decision_sha"].items():
        check(digest(READER / f"{key}_decisions.json") == checksum, "panel decision SHA in sidecar receipt")
    check_files(SOURCE / "inputs", receipt["sources"])
    refs = read(refpath)
    check(len(refs) == receipt["n"], "sidecar count")
    by_file = collections.defaultdict(list)
    for row in packets:
        by_file[row["file"]].append(row)
    data = {}
    for name, group in by_file.items():
        path = SOURCE / "archive_inputs" / name
        table = parquet.ParquetFile(path)
        needed = {p["local_index"] for p in group}; loaded = {}; offset = 0
        for batch in table.iter_batches(columns=["repo_name", "file_path", "code", "gold_snippet_index", "context"], batch_size=64):
            for j in sorted(i for i in needed if offset <= i < offset + len(batch)):
                loaded[j] = batch.slice(j-offset,1).to_pylist()[0]
            offset += len(batch)
        for p in group:
            raw = loaded[p["local_index"]]
            repo, path, line, gold, code_sha = refs[p["id"]]
            check(repo == raw["repo_name"] and path == raw["file_path"], "sidecar source path")
            check(hashlib.sha256(raw["code"].encode()).hexdigest() == code_sha, "sidecar code hash")
            check(raw["gold_snippet_index"] == gold and type(line) is str, "sidecar gold and index")
            raw["next_line"] = line
            check(raw["repo_name"] == p["repo"], "parquet project")
            check(p["id"] == f'{p["panel"]}|{p["local_index"]}', "row ID")
            check(sorted(p["rank"]) == list(range(len(raw["context"]))), "ranks not a permutation")
            data[p["id"]] = raw
    return data


def read_responses(panel):
    assignment = read(READER / f"{panel}_assignment.json")
    decisions = read(READER / f"{panel}_decisions.json")
    calls = READER / f"{panel}_calls"
    check_files(READER, read(READER / f"{panel}_input_lock.json"))
    check_files(calls, decisions)
    ids = {cid for arms in assignment.values() for cid in arms.values()}
    check(set(decisions) == {cid + ".json.gz" for cid in ids} == {p.name for p in calls.glob("*.json.gz")}, "physical call coverage")
    payload = {}
    for cid in ids:
        doc = read(calls / (cid + ".json.gz"))
        req = doc["request"]
        stable = json.dumps(req, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        check(hashlib.sha256(stable).hexdigest() == cid, "request body hash")
        choices = doc["reply"]["choices"]
        check(len(choices) == 1, "responses per prompt")
        message = choices[0]["message"].get("content") or ""
        payload[cid] = (req["messages"][-1]["content"], extract(message), doc["reply"]["usage"]["prompt_tokens"],
                        choices[0].get("finish_reason"), len(lines(message)), doc["reply"]["usage"]["completion_tokens"])
    return assignment, payload


def exact_discordants(plus, minus):
    n = plus + minus
    return min(1., 2 * sum(math.comb(n, x) for x in range(min(plus, minus) + 1)) / 2**n)


def audit(panel, packets):
    assignment, calls = read_responses(panel)
    check(set(assignment) == {p["id"] for p in packets}, "assignment/task set")
    golds = source_rows(packets)
    roles = read(HERE / "ast_roles.json")["records"][panel]
    results = []
    for p in packets:
        raw = golds[p["id"]]
        gold = raw["next_line"].strip()
        check(bool(gold), "empty gold")
        ctx = p["ctx"]
        item = {"id": p["id"], "panel": p["panel"], "ctx": overlap(ctx, gold), "arms": {},
                "edge_found": p["edge_event"] is not None, "graph_retrieved": p["rank"][0] == raw["gold_snippet_index"]}
        e = p["edge_event"]
        item["source_shows_type"] = item["display_shows_type"] = None
        if e is not None:
            check(e["source"] in p["rank"][1:], "edge provenance")
            manual = raw["context"][e["source"]].splitlines()[e["line"]]
            check(e["root"].lower() in manual.lower(), "type mention absent in source")
            # Application heuristic uses case-insensitive textual mentions. Test whether the exact case-sensitive
            # Java token survived clipping. This textual test does not resolve types or overloads.
            canonical = roles[p["id"]]["target_spelling"]
            pattern = r"(?<![A-Za-z0-9_$])" + re.escape(canonical) + r"(?![A-Za-z0-9_$])" if canonical else r"(?!)"
            item["source_shows_type"] = bool(re.search(pattern, manual))
            marker = "\n// Usage in another fragment\n"
            witness = p["snippets"]["edge"][0].rpartition(marker)[2] if marker in p["snippets"]["edge"][0] else ""
            item["display_shows_type"] = bool(re.search(pattern, witness))
        for name, (text, sn_tokens) in p["snippets"].items():
            check(0 <= sn_tokens <= 256, "evidence limit")
            cid = assignment[p["id"]][name]
            prompt, answer, tokens, finish, n_lines, out_tokens = calls[cid]
            check(prompt == "External Java fragment:\n" + text + "\n\nLast lines of current file:\n" + ctx + "\n\nNext source line:", "sealed prompt differs")
            item["arms"][name] = {"cid": cid, "em": answer == gold, "es": round(similarity_float(answer, gold)),
                                  "id_f1": idf1(answer, gold), "prompt_tokens": tokens, "completion_tokens": out_tokens,
                                  "evidence_tokens": sn_tokens, "finish": finish, "output_nonempty_lines": n_lines,
                                  "external": overlap(text, gold)}
        results.append(item)
    methods = {}
    for a in results[0]["arms"]:
        v = [x["arms"][a] for x in results]
        methods[a] = {"em_count": sum(z["em"] for z in v), "em_percent": 100*sum(z["em"] for z in v)/len(v),
                      **{field: sum(z[field] for z in v)/len(v) for field in ("es", "id_f1", "prompt_tokens", "completion_tokens", "evidence_tokens")},
                      "literal_external": sum(z["external"]["exact"] for z in v),
                      "near_external": sum(z["external"]["near"] for z in v),
                      "near_external_without_exact": sum(z["external"]["near"] and not z["external"]["exact"] for z in v),
                      "finish": dict(collections.Counter(z["finish"] for z in v)),
                      "returned_multiple_nonempty_lines": sum(z["output_nonempty_lines"]>1 for z in v)}
    detail = {}
    for a, b in (("edge", "local"), ("edge", "head"), ("local", "head"), ("portfolio", "four_head")):
        if a not in methods: continue
        groups = collections.defaultdict(list)
        for x in results:
            l, r = x["arms"][a], x["arms"][b]
            groups["all"].append(x)
            groups["changed_prompt" if l["cid"] != r["cid"] else "same_prompt"].append(x)
            groups["near_or_literal_in_visible_text" if any(c["near"] or c["exact"] for c in (l["external"], r["external"], x["ctx"])) else "no_near_or_literal_in_visible_text"].append(x)
        def compare(group):
            wins=sum(x["arms"][a]["em"] > x["arms"][b]["em"] for x in group)
            losses=sum(x["arms"][a]["em"] < x["arms"][b]["em"] for x in group)
            return {"n":len(group),"wins":wins,"losses":losses,"delta_em_pp":100*(wins-losses)/len(group),"exact_p":exact_discordants(wins,losses)}
        detail[a + "_vs_" + b] = {k:compare(v) for k,v in groups.items()}
    file_out = HERE / f"{panel}_audit_items.json.gz"
    file_out.write_bytes(gzip.compress(json.dumps(results, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(), mtime=0))
    return {"n":len(results),"physical_calls":len(calls),"logical_calls":sum(len(v) for v in assignment.values()),
            "reference_in_local_context":sum(x["ctx"]["exact"] for x in results),"near_eligible":sum(x["ctx"]["near_eligible"] for x in results),
            "near_in_local_context":sum(x["ctx"]["near"] for x in results),
            "edge_found":sum(x["edge_found"] for x in results), "source_shows_type":sum(x["source_shows_type"] is True for x in results),
            "display_shows_type":sum(x["display_shows_type"] is True for x in results),
            "methods":methods,"comparisons":detail,"item_sha256":digest(file_out),
            "locks":{f:digest(READER / f"{panel}_{f}.json") for f in ("data_lock","input_lock","decisions")}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("panels", choices=["A", "B", "both", "inputs"])
    args = parser.parse_args()
    both = {s:load_inputs(s) for s in ("A", "B")}
    check(not ({p["repo"] for p in both["A"]} & {p["repo"] for p in both["B"]}), "A/B project overlap")
    visible = {k: {"n":len(v),"different_edge_local":sum(row["snippets"]["edge"][0]!=row["snippets"]["local"][0] for row in v),
                    "edges":sum(row["edge_event"] is not None for row in v)} for k,v in both.items()}
    if args.panels == "inputs":
        print(json.dumps(visible)); return
    panels = ["A","B"] if args.panels=="both" else [args.panels]
    for p in panels:
        check((READER / f"{p}_decisions.json").exists(), f"{p} responses have not been sealed")
    for p in panels:
        result = audit(p, both[p])
        result.update({"target_sidecar_sha256":digest(READER / "original_targets.json.gz"),"script_sha256":digest(Path(__file__)), "utc": datetime.datetime.now(datetime.UTC).isoformat(),
                       "project_overlap_A_B":0})
        (HERE / f"{p}_audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
        print(p, result["n"], result["physical_calls"], {k:v["em_count"] for k,v in result["methods"].items()})
if __name__ == "__main__":
    main()






