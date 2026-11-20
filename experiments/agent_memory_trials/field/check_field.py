"""Post-hoc independent verification from immutable upstream histories. Never execute their commands."""
import collections
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parent
HEAD = re.compile(r"\|\s*head(?:\s+(?:-(\d+)|(?:-n|--lines)\s+(\d+)))?\s*$")
SEARCH = re.compile(r"(?:^|[\s;&|])(?:rg|grep)\s")


def get_original(row):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(row["url"], timeout=25) as response:
                data = response.read()
            break
        except OSError:
            if attempt == 2:
                raise
    assert hashlib.sha256(data).hexdigest() == row["sha256"]
    original = json.loads(data)
    by_id = {e["tool_call_id"]: e for e in row["events"]}
    paired, staged = {}, []
    for number, message in enumerate(original["messages"]):
        for call in message.get("tool_calls") or []:
            f = call.get("function", {})
            if f.get("name") == "bash":
                cmd = json.loads(f["arguments"]).get("command")
                if isinstance(cmd, str):
                    paired[call["id"]] = (number, cmd)
        cid = message.get("tool_call_id")
        if message.get("role") != "tool" or cid not in paired:
            continue
        number, cmd = paired.pop(cid)
        event = by_id.get(cid)
        extra = message.get("extra") or {}
        raw = extra.get("raw_output")
        n = (raw.count("\n") + int(bool(raw) and not raw.endswith("\n"))) if isinstance(raw, str) else None
        if event:
            assert event["command"] == cmd and event["message_index"] == number
            assert event["return_code"] == extra.get("returncode")
        head = HEAD.search(cmd)
        limit = int(next((x for x in head.groups() if x), "10")) if head else None
        marked = event["parse"]["limits"] if event else []
        if marked:
            assert marked == [["stdout_head", limit]]
        staged.append(dict(index=number, id=cid, command=cmd, head=limit, recognized=bool(event), recorded_limits=marked,
                           output_lines=n, rc=extra.get("returncode")))
    assert len(staged) == row["matched"] + row["other_bash_with_result"]
    assert len(paired) == row["no_result"]
    assert sum(e["recognized"] for e in staged) == row["matched"]
    replay = verify_eodag_text(original) if row["path"].endswith("cs-si__eodag-616.traj.json") else None
    return dict(path=row["path"], repo=row["repo"], sha256=row["sha256"], events=staged, replay=replay)


def verify_eodag_text(original):
    # Independently implement the specific literal alternatives; never evaluate shell input.
    ms = original["messages"]
    assert [m["role"] for m in ms[14:17]] == ["assistant", "tool", "assistant"]
    cat_call, = ms[14]["tool_calls"]
    cat_cmd = json.loads(cat_call["function"]["arguments"])["command"]
    assert cat_cmd == "cd /eodag && cat eodag/plugins/search/qssearch.py"
    raw_source = ms[15]["extra"]["raw_output"]
    assert ms[15]["tool_call_id"] == cat_call["id"] and ms[15]["extra"]["returncode"] == 0
    head_call = ms[16]["tool_calls"][0]
    cmd = json.loads(head_call["function"]["arguments"])["command"]
    assert cmd == r'cd /eodag && grep -n "class\|def \|per_product\|metadata\|ODataV4" eodag/plugins/search/qssearch.py | head -80'
    result = next(m for m in ms if m.get("tool_call_id") == head_call["id"])
    assert result["extra"]["returncode"] == 0
    raw_result = result["extra"]["raw_output"]
    pattern = re.compile(r"class|def |per_product|metadata|ODataV4")
    rows = [f"{num}:{line}" for num,line in enumerate(raw_source.splitlines(),1) if pattern.search(line)]
    assert rows[:80] == raw_result.splitlines() and len(rows) > 80
    return dict(source_message=14, source_tool_id=cat_call["id"], search_message=16, search_tool_id=head_call["id"],
                source_lines=len(raw_source.splitlines()), matching_lines_in_prior_file_output=len(rows),
                returned_lines=len(raw_result.splitlines()), omitted_lines=len(rows)-80,
                last_returned_source_line=int(rows[79].split(":",1)[0]),
                first_omitted_source_line=int(rows[80].split(":",1)[0]), full_visible_prefix_exact_match=True,
                source_output_sha256=hashlib.sha256(raw_source.encode()).hexdigest(),
                search_output_sha256=hashlib.sha256(raw_result.encode()).hexdigest())


def choose(examples, name, selected):
    for r, e in examples:
        if all(r["repo"] != x["repo"] for x in selected):
            break
    else:
        r, e = examples[0]
    selected.append(dict(kind=name, repo=r["repo"], source_path=r["path"], source_sha256=r["sha256"],
                         message_index=e["index"], tool_call_id=e["id"], command=e["command"],
                         found_by_frozen_parser=e["recognized"], head_lines=e["head"], raw_output_lines=e["output_lines"],
                         shell_rc=e["rc"]))


def main():
    records = [json.loads(x) for x in (ROOT / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        upstream = list(executor.map(get_original, records))
    events = [(r, e) for r in upstream for e in r["events"]]
    limited = [(r, e) for r, e in events if e["recorded_limits"]]
    comparison = collections.Counter("missing" if e["output_lines"] is None else
                                     "below" if e["output_lines"] < e["head"] else
                                     "above" if e["output_lines"] > e["head"] else "equal" for _, e in limited)
    # Curated example strata; selected in corpus order and, where possible, distinct projects.
    selected = []
    choose([(r,e) for r,e in limited if e["head"] == e["output_lines"]], "limit reached", selected)
    choose([(r,e) for r,e in limited if 0 < e["output_lines"] < e["head"]], "below limit", selected)
    choose([(r,e) for r,e in limited if e["output_lines"] == 0], "empty output with explicit cap", selected)
    choose([(r,e) for r,e in events if e["recognized"] and not e["recorded_limits"] and len(e["command"]) < 150
            and all(c not in e["command"] for c in "\n\r;|")], "recognized uncapped command", selected)
    excluded = [(r,e) for r,e in events if not e["recognized"] and SEARCH.search(e["command"]) and len(e["command"]) < 210
                and "\n" not in e["command"] and "\r" not in e["command"]]
    choose([(r,e) for r,e in excluded if e["head"] and "2>/dev/null" in e["command"]], "excluded search with redirection and head", selected)
    choose([(r,e) for r,e in excluded if "xargs grep" in e["command"]], "excluded xargs search", selected)
    choose([(r,e) for r,e in excluded if " | " in e["command"] and e["command"].startswith("grep") and not e["head"]
            and ("| sort" in e["command"] or "| grep" in e["command"])], "excluded downstream transform", selected)
    choose([(r,e) for r,e in excluded if not e["head"] and "2>/dev/null" in e["command"]], "excluded uncapped redirected search", selected)
    h = sum(any(e["recorded_limits"] for e in r["events"]) for r in upstream)
    available = sum(e["output_lines"] is not None for _,e in limited)
    result = dict(revision="11164976b4f920cdb0d0cd570ca572e49acea1e8", source_sha256_verified=len(upstream),
                  matched_bash_tool_responses=len(events), frozen_recognized=sum(e["recognized"] for _, e in events),
                  explicit_caps_confirmed=len(limited), histories_with_caps=h, cap_kind="trailing stdout head",
                  cap_response_lines_available=available, recorded_lines_vs_syntactic_head_cap=dict(comparison),
                  rc_for_capped=collections.Counter(str(e["rc"]) for _,e in limited),
                  histories_reaching_at_least_one_cap=sum(any(e["recorded_limits"] and e["head"] == e["output_lines"] for e in r["events"]) for r in upstream),
                  eodag_same_history_matching_replay=next(r["replay"] for r in upstream if r["replay"]), examples=selected)
    (ROOT / "verification_examples.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
