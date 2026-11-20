"""Join native model-accounting events to finished episodes and official per-task grades."""
import collections
import hashlib
import json
import re
from pathlib import Path
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
CODEC = ROOT.parents[1] / "memory_session5/live/tokenizer.json"

def read(path):
    return json.loads(path.read_bytes())

def main():
    grade = read(ROOT / "grading/results.json")
    assert grade["complete"] and len(grade["rows"]) == 10
    official = {(r["instance"], r["method"]): r for r in grade["rows"]}
    requests = [json.loads(line) for line in (ROOT / "requests.jsonl").read_bytes().splitlines()]
    codec = Tokenizer.from_file(str(CODEC))
    assigned = set()
    rows = []
    for iid, method in read(ROOT / "order.json"):
        episode = ROOT / "episodes/python" / iid / method / "seed0"
        interval = read(episode / "finished.json")
        traj = read(episode / (iid + ".traj.json"))
        calls = [(i, e) for i, e in enumerate(requests) if interval["start_ts"] <= e["epoch"] <= interval["end_ts"]]
        indices = {i for i, _ in calls}
        assert indices.isdisjoint(assigned)
        assigned.update(indices)
        events = [e for _, e in calls]
        assert events and all(e["http_status"] == 200 for e in events)
        turns = [e["turn"] for e in events]
        assert turns[0] == 0 and all(b-a in (0,1) for a,b in zip(turns,turns[1:]))
        assert len(events) == traj["info"]["model_stats"]["api_calls"]
        commands = []
        for msg in traj["messages"]:
            for call in msg.get("tool_calls") or []:
                if call["function"]["name"] == "bash":
                    commands.append(json.loads(call["function"]["arguments"])["command"])
        searches = [cmd.strip() for cmd in commands if re.search(r"(?:^|[;&|]\s*|\s)(?:rg|grep|find)\s", cmd)]
        messages = traj["messages"]
        material = ROOT / "memories" / method / "python" / iid
        mem = (material / "memory.txt").read_text(encoding="utf8").strip() if method != "base" else ""
        cards = read(material / "memory.json")["retrieved"] if mem else []
        if mem:
            assert all(card["content"].strip() in messages[1]["content"] for card in cards)
        res = official[(iid,method)]
        rows.append(dict(instance=iid, method=method, official_status=res["status"], measured_f2p=res["measured_F2P"],
                         lost_p2p=res["measured_P2P_lost"], total_p2p=res["expected_P2P"],
                         candidate_bytes=res["patch_bytes"], execution_stage=res["execution_stage"],
                         exit_status=traj["info"]["exit_status"], model_calls=len(events), repeated_turn_indices=[t for t,n in collections.Counter(turns).items() if n>1], bash_commands=len(commands),
                         search_commands=len(searches), identical_search_repeats=len(searches)-len(set(searches)),
                         input_tokens=sum(e["usage"]["prompt_tokens"] for e in events),
                         output_tokens=sum(e["usage"]["completion_tokens"] for e in events),
                         input_first=events[0]["usage"]["prompt_tokens"], seconds=interval["duration_s"],
                         proxy_seconds=round(sum(e["seconds"] for e in events),2),
                         card_tokens=[len(codec.encode(c["content"],add_special_tokens=False).ids) for c in cards],
                         card_ids=[c["id"] for c in cards], elapsed_memory_build_search_s=read(material / "memory.json")["elapsed_seconds"] if cards else 0))
    assert assigned == set(range(len(requests)))
    for iid in {r["instance"] for r in rows}:
        assert len({tuple(r["card_ids"]) for r in rows if r["instance"]==iid and r["method"]!="base"}) == 1
    result=dict(rows=rows, total_calls=len(requests), total_input=sum(r["input_tokens"] for r in rows),
                total_output=sum(r["output_tokens"] for r in rows), tokenizer_sha256=hashlib.sha256(CODEC.read_bytes()).hexdigest(),
                request_sha256=hashlib.sha256((ROOT / "requests.jsonl").read_bytes()).hexdigest(),
                score_source="grading/results.json", episode_assignment="start_ts <= proxy request epoch <= end_ts")
    (ROOT / "results.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    print(json.dumps(result, ensure_ascii=False))
if __name__ == "__main__":
    main()
